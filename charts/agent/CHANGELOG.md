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
