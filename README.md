# Checkly Helm Charts

## Usage

[Helm](https://helm.sh) must be installed to use the charts. Please refer to Helm's [documentation](https://helm.sh/docs) to get started.

Once Helm has been set up correctly, add the repo as follows:

    helm repo add checkly https://checkly.github.io/helm-charts

If you had already added this repo earlier, run `helm repo update` to retrieve the latest versions of the packages. You can then run `helm search repo checkly` to see the charts.

To install a chart, for example the agent chart:

    helm install my-agent checkly/agent

To uninstall the chart:

    helm uninstall my-agent

See [https://github.com/checkly/helm-charts](https://github.com/checkly/helm-charts) for more info and available charts.
