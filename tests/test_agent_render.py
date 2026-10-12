import base64
from pathlib import Path
import subprocess
import tempfile
import unittest

import yaml

CHART = Path(__file__).resolve().parents[1] / "charts" / "agent"
RELEASE = "ci-agent"
NAMESPACE = "checkly-agent"


class UniqueKeyLoader(yaml.SafeLoader):
    def construct_mapping(self, node, deep=False):
        result = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            if key in result:
                raise ValueError(f"Duplicate YAML key: {key}")
            result[key] = self.construct_object(value_node, deep=deep)
        return result


def render_result(values=None, release=RELEASE):
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml") as settings:
        yaml.safe_dump(values or {}, settings)
        settings.flush()
        return subprocess.run(
            ["helm", "template", release, str(CHART), "--namespace", NAMESPACE,
             "--values", settings.name],
            text=True, capture_output=True, check=False,
        )


def render(values=None, release=RELEASE):
    result = render_result(values, release)
    if result.returncode:
        raise AssertionError(result.stderr)
    docs = {}
    for doc in yaml.load_all(result.stdout, Loader=UniqueKeyLoader):
        if doc is None:
            continue
        kind = doc["kind"]
        if kind in docs:
            raise AssertionError(f"Unexpected second {kind}")
        docs[kind] = doc
    return docs


def autoscaling(**overrides):
    return {"autoscaling": {
        "enabled": True,
        "privateLocationSlugName": "test-location",
        "prometheus": {"serverAddress": "http://prometheus:9090"},
        **overrides,
    }}


def pod(docs):
    return docs["Deployment"]["spec"]["template"]["spec"]


def container(docs):
    return pod(docs)["containers"][0]


def trigger(docs):
    triggers = docs["ScaledObject"]["spec"]["triggers"]
    if len(triggers) != 1:
        raise AssertionError(f"Expected one trigger, got {len(triggers)}")
    return triggers[0]


class ScaledObjectTests(unittest.TestCase):
    def test_default_scaler(self):
        docs = render(autoscaling())
        self.assertEqual(set(docs), {"Deployment", "Secret", "ScaledObject"})
        scaled = docs["ScaledObject"]
        self.assertEqual(scaled["apiVersion"], "keda.sh/v1alpha1")
        self.assertEqual(scaled["metadata"]["name"], docs["Deployment"]["metadata"]["name"])
        self.assertEqual(scaled["spec"]["scaleTargetRef"], {"name": "ci-agent"})
        self.assertNotIn("replicas", docs["Deployment"]["spec"])
        self.assertEqual(scaled["spec"]["minReplicaCount"], 2)
        self.assertEqual(scaled["spec"]["maxReplicaCount"], 10)
        self.assertNotIn("pollingInterval", scaled["spec"])
        self.assertEqual(trigger(docs), {
            "type": "prometheus",
            "metadata": {
                "serverAddress": "http://prometheus:9090",
                "metricName": "checkly_private_location_check_runs",
                "threshold": "1",
                "query": 'sum(checkly_private_location_check_runs{state=~"queued|inflight", private_location_slug_name="test-location"})',
            },
        })
        behavior = scaled["spec"]["advanced"]["horizontalPodAutoscalerConfig"]["behavior"]
        policy = [{"type": "Pods", "value": 1, "periodSeconds": 60}]
        self.assertEqual(behavior, {
            "scaleUp": {"policies": policy},
            "scaleDown": {"selectPolicy": "Min", "policies": policy},
        })

    def test_name_override_changes_only_scaler_name(self):
        default = render(autoscaling())
        custom = render(autoscaling(scaledObject={"name": "ci-agent-scaler"}))
        self.assertEqual(custom["ScaledObject"]["metadata"]["name"], "ci-agent-scaler")
        custom["ScaledObject"]["metadata"]["name"] = default["ScaledObject"]["metadata"]["name"]
        self.assertEqual(custom, default)

    def test_empty_name_uses_deployment_name(self):
        docs = render({**autoscaling(scaledObject={"name": ""}), "fullnameOverride": "custom-agent"})
        self.assertEqual(docs["ScaledObject"]["metadata"]["name"], "custom-agent")
        self.assertEqual(docs["ScaledObject"]["spec"]["scaleTargetRef"]["name"], "custom-agent")

    def test_fullname_override_keeps_custom_scaler_name(self):
        docs = render({**autoscaling(scaledObject={"name": "custom-scaler"}), "fullnameOverride": "custom-agent"})
        self.assertEqual(docs["Deployment"]["metadata"]["name"], "custom-agent")
        self.assertEqual(docs["ScaledObject"]["metadata"]["name"], "custom-scaler")
        self.assertEqual(docs["ScaledObject"]["spec"]["scaleTargetRef"]["name"], "custom-agent")

    def test_disabled_autoscaling_keeps_replicas(self):
        docs = render({"replicaCount": 4, "autoscaling": {"scaledObject": {"name": "unused"}}})
        self.assertNotIn("ScaledObject", docs)
        self.assertEqual(docs["Deployment"]["spec"]["replicas"], 4)

    def test_external_scaler_needs_no_prometheus_settings(self):
        docs = render({"replicaCount": 4, "autoscaling": {
            "enabled": True, "scaledObject": {"create": False, "name": "external"},
        }})
        self.assertNotIn("ScaledObject", docs)
        self.assertNotIn("replicas", docs["Deployment"]["spec"])

    def test_replica_limits_and_polling_interval(self):
        docs = render(autoscaling(minReplicaCount=0, maxReplicaCount=20, pollingInterval=15))
        spec = docs["ScaledObject"]["spec"]
        self.assertEqual((spec["minReplicaCount"], spec["maxReplicaCount"], spec["pollingInterval"]), (0, 20, 15))

    def test_threshold_precedence_and_string_type(self):
        for threshold, concurrency, expected in [("", None, "1"), ("", 8, "8"), (3, 8, "3"), ("2.5", 8, "2.5")]:
            with self.subTest(threshold=threshold, concurrency=concurrency):
                values = autoscaling(threshold=threshold)
                if concurrency is not None:
                    values["env"] = {"JOB_CONCURRENCY": concurrency}
                self.assertEqual(trigger(render(values))["metadata"]["threshold"], expected)

    def test_templated_query_and_threshold(self):
        docs = render({**autoscaling(
            privateLocationSlugName="",
            query='sum(check_runs{namespace="{{ .Release.Namespace }}",location="{{ .Values.env.LOCATION }}"})',
            threshold="{{ .Values.env.JOB_CONCURRENCY }}",
        ), "env": {"JOB_CONCURRENCY": 6, "LOCATION": "custom"}})
        metadata = trigger(docs)["metadata"]
        self.assertEqual(metadata["threshold"], "6")
        self.assertEqual(metadata["query"], 'sum(check_runs{namespace="checkly-agent",location="custom"})')

    def test_authentication_and_extra_metadata(self):
        auth = {"name": "prometheus-auth", "kind": "ClusterTriggerAuthentication"}
        docs = render(autoscaling(prometheus={
            "serverAddress": "https://prometheus:9090",
            "authenticationRef": auth,
            "metadata": {"authModes": "basic", "unsafeSsl": True, "activationThreshold": 2},
        }))
        self.assertEqual(trigger(docs)["authenticationRef"], auth)
        metadata = trigger(docs)["metadata"]
        self.assertEqual(metadata["serverAddress"], "https://prometheus:9090")
        self.assertEqual(metadata["authModes"], "basic")
        self.assertEqual(metadata["unsafeSsl"], "true")
        self.assertEqual(metadata["activationThreshold"], "2")

    def test_custom_behavior(self):
        docs = render(autoscaling(behavior={"scaleDown": {"stabilizationWindowSeconds": 120}}))
        behavior = docs["ScaledObject"]["spec"]["advanced"]["horizontalPodAutoscalerConfig"]["behavior"]
        self.assertEqual(behavior["scaleDown"]["stabilizationWindowSeconds"], 120)

    def test_null_behavior_omits_advanced(self):
        self.assertNotIn("advanced", render(autoscaling(behavior=None))["ScaledObject"]["spec"])

    def test_required_prometheus_address(self):
        for query in ["", "sum(custom_metric)"]:
            with self.subTest(query=query):
                result = render_result(autoscaling(prometheus={"serverAddress": ""}, query=query))
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("autoscaling.prometheus.serverAddress is required", result.stderr)

    def test_required_slug_for_default_query(self):
        result = render_result(autoscaling(privateLocationSlugName=""))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("autoscaling.privateLocationSlugName is required", result.stderr)


class DeploymentTests(unittest.TestCase):
    def test_defaults(self):
        docs = render()
        self.assertEqual(set(docs), {"Deployment", "Secret"})
        deployment = docs["Deployment"]
        self.assertEqual(deployment["apiVersion"], "apps/v1")
        self.assertEqual(deployment["spec"]["replicas"], 1)
        self.assertEqual(deployment["spec"]["strategy"], {
            "type": "RollingUpdate", "rollingUpdate": {"maxSurge": "10%", "maxUnavailable": 0},
        })
        self.assertEqual(pod(docs)["terminationGracePeriodSeconds"], 330)
        self.assertIs(pod(docs)["shareProcessNamespace"], False)
        chart = yaml.safe_load((CHART / "Chart.yaml").read_text())
        self.assertEqual(container(docs)["image"], f'docker.io/checkly/agent:{chart["appVersion"]}')
        self.assertEqual(container(docs)["imagePullPolicy"], "IfNotPresent")
        self.assertEqual(container(docs)["ports"], [{"name": "metrics", "containerPort": 8080}])
        for key in ["livenessProbe", "readinessProbe", "resources", "volumeMounts", "securityContext"]:
            self.assertNotIn(key, container(docs))
        for key in ["volumes", "imagePullSecrets", "securityContext", "nodeSelector", "affinity", "tolerations", "topologySpreadConstraints"]:
            self.assertNotIn(key, pod(docs))

    def test_names_labels_and_selectors(self):
        cases = [({}, RELEASE, "ci-agent", "agent"),
                 ({"nameOverride": "worker"}, "ci", "ci-worker", "worker"),
                 ({"fullnameOverride": "custom-agent"}, "ci", "custom-agent", "agent"),
                 ({"fullnameOverride": "a" * 62 + "-suffix"}, "ci", "a" * 62, "agent")]
        for settings, release, expected, label in cases:
            with self.subTest(settings=settings):
                docs = render({**autoscaling(), **settings, "podDisruptionBudget": {"enabled": True, "minAvailable": 1}}, release)
                deployment = docs["Deployment"]
                selector = {"app.kubernetes.io/name": label, "app.kubernetes.io/instance": release}
                self.assertEqual(deployment["spec"]["selector"]["matchLabels"], selector)
                self.assertEqual(docs["PodDisruptionBudget"]["spec"]["selector"]["matchLabels"], selector)
                for kind in ["Deployment", "ScaledObject", "PodDisruptionBudget"]:
                    self.assertEqual(docs[kind]["metadata"]["name"], expected)
                    self.assertEqual(docs[kind]["metadata"]["namespace"], NAMESPACE)
                    self.assertEqual(docs[kind]["metadata"]["labels"], deployment["spec"]["template"]["metadata"]["labels"])
                for key, value in selector.items():
                    self.assertEqual(deployment["spec"]["template"]["metadata"]["labels"][key], value)
                self.assertEqual(docs["ScaledObject"]["spec"]["scaleTargetRef"]["name"], expected)

    def test_image_metrics_strategy_and_grace_period(self):
        strategy = {"type": "Recreate"}
        docs = render({"image": {"repository": "registry.example/agent", "tag": "test", "pullPolicy": "Always"},
                       "metrics": {"port": 9090}, "strategy": strategy, "terminationGracePeriodSeconds": 600})
        self.assertEqual(container(docs)["image"], "registry.example/agent:test")
        self.assertEqual(container(docs)["imagePullPolicy"], "Always")
        self.assertEqual(container(docs)["ports"][0]["containerPort"], 9090)
        self.assertEqual(docs["Deployment"]["spec"]["strategy"], strategy)
        self.assertEqual(pod(docs)["terminationGracePeriodSeconds"], 600)

    def test_environment_values_and_templates(self):
        docs = render({"env": {"COUNT": 5, "ENABLED": True, "LOCATION": "{{ .Release.Namespace }}",
                               "{{ .Release.Name | upper | replace \"-\" \"_\" }}": "{{ .Chart.Name }}"}})
        env = {entry["name"]: entry for entry in container(docs)["env"]}
        self.assertEqual(len(env), 5)
        for key, value in {"COUNT": "5", "ENABLED": "true", "LOCATION": NAMESPACE, "CI_AGENT": "agent"}.items():
            self.assertEqual(env[key], {"name": key, "value": value})
        self.assertIn("valueFrom", env["API_KEY"])

    def test_pod_metadata(self):
        annotations = {"example.com/config": "test"}
        labels = {"team": "platform"}
        docs = render({"podAnnotations": annotations, "podLabels": labels})
        metadata = docs["Deployment"]["spec"]["template"]["metadata"]
        self.assertEqual(metadata["annotations"], annotations)
        self.assertEqual(metadata["labels"]["team"], "platform")
        self.assertNotIn("team", docs["Deployment"]["spec"]["selector"]["matchLabels"])

    def test_container_options(self):
        settings = {
            "securityContext": {"runAsNonRoot": True, "runAsUser": 10001},
            "resources": {"requests": {"cpu": "100m", "memory": "128Mi"}, "limits": {"memory": "256Mi"}},
            "livenessProbe": {"httpGet": {"path": "/health", "port": "metrics"}, "initialDelaySeconds": 10},
            "readinessProbe": {"tcpSocket": {"port": "metrics"}},
            "volumeMounts": [{"name": "config", "mountPath": "/etc/config", "readOnly": True}],
        }
        actual = container(render(settings))
        for key, value in settings.items():
            self.assertEqual(actual[key], value, key)

    def test_pod_options(self):
        settings = {
            "imagePullSecrets": [{"name": "registry-auth"}],
            "podSecurityContext": {"fsGroup": 2000},
            "volumes": [{"name": "config", "secret": {"secretName": "agent-config"}}],
            "nodeSelector": {"kubernetes.io/os": "linux"},
            "affinity": {"nodeAffinity": {"requiredDuringSchedulingIgnoredDuringExecution": {
                "nodeSelectorTerms": [{"matchExpressions": [{"key": "pool", "operator": "In", "values": ["agents"]}]}],
            }}},
            "tolerations": [{"key": "agent", "operator": "Exists", "effect": "NoSchedule"}],
            "topologySpreadConstraints": [{"maxSkew": 1, "topologyKey": "kubernetes.io/hostname",
                                           "whenUnsatisfiable": "ScheduleAnyway", "labelSelector": {"matchLabels": {"app.kubernetes.io/name": "agent"}}}],
        }
        actual = pod(render(settings))
        for key, value in settings.items():
            self.assertEqual(actual["securityContext" if key == "podSecurityContext" else key], value, key)


class SecretTests(unittest.TestCase):
    def test_created_secret_and_reference(self):
        key = "test:key/with+symbols="
        docs = render({"apiKeySecret": {"apiKey": key}})
        secret = docs["Secret"]
        self.assertEqual(secret["apiVersion"], "v1")
        self.assertEqual(secret["metadata"], {"name": "ci-agent-auth", "namespace": NAMESPACE})
        self.assertEqual(base64.b64decode(secret["data"]["apiKey"]).decode(), key)
        self.assertEqual(container(docs)["env"], [{"name": "API_KEY", "valueFrom": {
            "secretKeyRef": {"name": secret["metadata"]["name"], "key": "apiKey"},
        }}])

    def test_existing_secret(self):
        for key in [None, "token"]:
            with self.subTest(key=key):
                settings = {"create": False, "name": "existing-auth"}
                if key:
                    settings["key"] = key
                docs = render({"apiKeySecret": settings})
                self.assertNotIn("Secret", docs)
                self.assertEqual(container(docs)["env"][0]["valueFrom"]["secretKeyRef"], {
                    "name": "existing-auth", "key": key or "apiKey",
                })


class PodDisruptionBudgetTests(unittest.TestCase):
    def test_disabled_by_default(self):
        self.assertNotIn("PodDisruptionBudget", render())

    def test_null_limits_are_omitted(self):
        docs = render({"podDisruptionBudget": {
            "enabled": True, "minAvailable": None, "maxUnavailable": 1,
        }})
        self.assertNotIn("minAvailable", docs["PodDisruptionBudget"]["spec"])
        self.assertEqual(docs["PodDisruptionBudget"]["spec"]["maxUnavailable"], 1)

    def test_availability_limits(self):
        for key, other in [("minAvailable", "maxUnavailable"), ("maxUnavailable", "minAvailable")]:
            for value in [1, "50%", 0]:
                with self.subTest(key=key, value=value):
                    docs = render({"podDisruptionBudget": {"enabled": True, key: value}})
                    budget = docs["PodDisruptionBudget"]
                    self.assertEqual(budget["apiVersion"], "policy/v1")
                    self.assertEqual(budget["spec"][key], value)
                    self.assertNotIn(other, budget["spec"])
                    self.assertEqual(budget["spec"]["selector"], docs["Deployment"]["spec"]["selector"])


if __name__ == "__main__":
    unittest.main()
