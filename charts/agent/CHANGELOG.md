# Changelog

## 0.9.0

### Added

- Add optional `autoscaling.fallback` settings to the KEDA ScaledObject.

### Upgrade note

This release changes PodDisruptionBudget rendering: zero limits are now kept.
Earlier releases omitted `minAvailable: 0` and `maxUnavailable: 0`.

When `podDisruptionBudget.enabled` is `true`, set only one of `minAvailable` or
`maxUnavailable`. Remove the other field or set it to `null`. Kubernetes rejects
a budget with both fields set, even if one is zero.

Before upgrading, check your values. For example, if you use `minAvailable: 1`
with `maxUnavailable: 0`, remove `maxUnavailable` or set it to `null`:

```yaml
podDisruptionBudget:
  enabled: true
  minAvailable: 1
  maxUnavailable: null
```

## 0.8.0

- Add optional KEDA autoscaling with a Prometheus trigger.
- Add settings for scaling limits, polling, HPA behavior, queries, and authentication.
- Omit Deployment `spec.replicas` when autoscaling is enabled.
- Add `autoscaling.scaledObject.create: false` for an external ScaledObject or HPA.
- Change the default `terminationGracePeriodSeconds` from 300 to 330.

Upgrade note: when you first enable autoscaling, the replica count can drop to 1.
Set `autoscaling.minReplicaCount` to at least the current replica count for that
upgrade. Lower it in a later upgrade.

## 0.7.5

- Update the default agent image to 8.9.0.

## 0.7.4

- Update the default agent image to 8.8.0.

## 0.7.3

- Update the default agent image to 8.4.0.

## 0.7.2

- Update the default agent image to 8.3.3.

## 0.7.1

- Update the default agent image to 8.3.2.

## 0.7.0

- Update the default agent image to 8.3.0.

## 0.6.0

- Update the default agent image to 8.2.0.
- Change the example `securityContext.runAsUser` from 1000 to 10001.

## 0.5.0

- Update the default agent image to 8.1.0.

## 0.4.4

- Update the default agent image to 7.0.1.

## 0.4.3

- Update the default agent image to 7.0.0.

## 0.4.2

- Update the default agent image to 6.2.0.

## 0.4.1

- Update the default agent image to 6.1.5.

## 0.4.0

- Add optional PodDisruptionBudget settings.
- Add `topologySpreadConstraints` settings.
- Add pod anti-affinity and topology spread examples.

## 0.3.2

- Update the default agent image to 6.1.3.
- Expose the metrics container port. Set `metrics.port` to change the default of 8080.

## 0.3.1

- Add a Terraform installation example to the README.

## 0.3.0

- Add `apiKeySecret.key` to select the key in an existing Secret.

## 0.2.1

- Add Deployment `strategy` settings.
- Set the default rolling update to `maxSurge: 10%` and `maxUnavailable: 0`.

## 0.2.0

- Move `apiKeySecret` and `terminationGracePeriodSeconds` to the top level in values.
- Add `env` settings with template support for names and values.

Upgrade note: remove the `agent` parent key from `apiKeySecret` and
`terminationGracePeriodSeconds` in your values.

## 0.1.1

- Set the Deployment and Secret namespace to the release namespace.
- Disable shared process namespaces in agent pods.
- Add `agent.terminationGracePeriodSeconds` with a default of 300.

## 0.1.0

- Add the initial agent chart with default agent image 6.0.7.
- Add Deployment and API key Secret templates.
