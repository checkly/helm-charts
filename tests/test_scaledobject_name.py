from pathlib import Path
import re
import subprocess
import unittest

CHART = Path(__file__).resolve().parents[1] / "charts" / "agent"


def render(*settings):
    args = ["helm", "template", "ci-agent", str(CHART), "--namespace", "checkly-agent"]
    for setting in settings:
        args.extend(["--set", setting])
    output = subprocess.check_output(args, text=True)
    return {
        re.search(r"^kind: (.+)$", doc, re.MULTILINE)[1]: doc
        for doc in re.split(r"(?:^|\n)---\n", output)
        if re.search(r"^kind: (.+)$", doc, re.MULTILINE)
    }


def name(doc):
    return re.search(r"^  name: (.+)$", doc, re.MULTILINE)[1].strip('"')


class ScaledObjectNameTests(unittest.TestCase):
    settings = (
        "autoscaling.enabled=true",
        "autoscaling.privateLocationSlugName=test-location",
        "autoscaling.prometheus.serverAddress=http://prometheus:9090",
    )

    def test_default_name_matches_deployment(self):
        docs = render(*self.settings)
        self.assertEqual(name(docs["ScaledObject"]), name(docs["Deployment"]))

    def test_override_preserves_deployment_and_target(self):
        default = render(*self.settings)
        custom = render(*self.settings, "autoscaling.scaledObject.name=ci-agent-scaler")
        self.assertEqual(name(custom["ScaledObject"]), "ci-agent-scaler")
        self.assertEqual(custom["Deployment"], default["Deployment"])
        target = re.search(r"scaleTargetRef:\n    name: (.+)", custom["ScaledObject"])[1]
        self.assertEqual(target, name(custom["Deployment"]))

    def test_fullname_override_changes_target_only(self):
        docs = render(*self.settings, "fullnameOverride=custom-agent", "autoscaling.scaledObject.name=custom-scaler")
        self.assertEqual(name(docs["Deployment"]), "custom-agent")
        self.assertEqual(name(docs["ScaledObject"]), "custom-scaler")
        self.assertIn("scaleTargetRef:\n    name: custom-agent", docs["ScaledObject"])

    def test_disabled_autoscaling_keeps_replicas(self):
        docs = render("autoscaling.scaledObject.name=unused")
        self.assertNotIn("ScaledObject", docs)
        self.assertIn("  replicas: 1\n", docs["Deployment"])

    def test_external_scaler_does_not_render_object(self):
        docs = render("autoscaling.enabled=true", "autoscaling.scaledObject.create=false", "autoscaling.scaledObject.name=external")
        self.assertNotIn("ScaledObject", docs)
        self.assertNotIn("  replicas:", docs["Deployment"])


if __name__ == "__main__":
    unittest.main()
