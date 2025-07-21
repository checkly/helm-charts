# Checkly Agent Helm Chart

This helm chart deploys the Checkly agent to create your own [private location](https://www.checklyhq.com/docs/private-locations/).

## Prerequisites

Create a private location as described [here](https://www.checklyhq.com/docs/private-locations/#configuring-a-private-location) to get a agent api key.

## Usage

[Helm](https://helm.sh) must be installed to use the charts. Please refer to Helm's [documentation](https://helm.sh/docs) to get started.

Once Helm has been set up correctly, add the repo as follows:

    helm repo add checkly https://checkly.github.io/helm-charts

If you had already added this repo earlier, run `helm repo update` to retrieve the latest versions of the packages.

To install the agent chart:

    helm upgrade --install my-agent checkly/agent --set apiKeySecret.apiKey=pl_...

To uninstall the chart:

    helm uninstall my-agent

See [https://github.com/checkly/helm-charts](https://github.com/checkly/helm-charts) for more info and available charts.

## Alternative ways to set the agent API Key

Instead of setting `apiKeySecret.apiKey` you can also choose an existing secret with the following options

```
apiKeySecret:
  create: false
  name: <NAME_OF_EXISTING_SECRET>
```

or create the secret with `extraManifests`

```
apiKeySecret:
  create: false
  name: checkly-agent-secret

extraManifests:
  - apiVersion: external-secrets.io/v1beta1
    kind: ExternalSecret
    metadata:
      name: checkly-agent-secret
      namespace: monitoring
    spec:
      target:
        name: my-checkly-secret-in-aws
```
