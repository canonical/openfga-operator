# Changelog

## 1.0.0 (2025-03-10)


### Features

* add openfga lib v1 ([e747890](https://github.com/canonical/openfga-operator/commit/e74789082ce81167163eb63e21208b54b912f0ee))
* **COS:** add Grafana dashboard, Loki alert rules and Alertmanager rules ([d8a3ec5](https://github.com/canonical/openfga-operator/commit/d8a3ec5192c9acc4081585fc319292de369fcc78))
* **COS:** COS integration first implementation ([f8d1d38](https://github.com/canonical/openfga-operator/commit/f8d1d38f4c4376d7d02d77e8061c9eace834313b))
* **COS:** implement bundle relations, log on promtail-digest-error, expose metrics port on OpenFGA service ([8d3a111](https://github.com/canonical/openfga-operator/commit/8d3a111963af5dcc5a62ae87d20ec4d0834cba92))
* enable response time histograms ([388e1e9](https://github.com/canonical/openfga-operator/commit/388e1e91e3a573dd66c9b4937e8c5f826bc373cb))
* switched to Loki log forwarding ([ac06e69](https://github.com/canonical/openfga-operator/commit/ac06e6991c9a82363c1cf7ffb60365b22f3ed0db))
* update openfga lib ([7e976ac](https://github.com/canonical/openfga-operator/commit/7e976ac126cd2b30b96e9c7a5e9fb49ffc00f07a))
* update to use openfga v1.5.2 ([edbbc75](https://github.com/canonical/openfga-operator/commit/edbbc755cabe9891b8d874e35ce130eb0cfe8897))
* use openfga lib v1 ([f5ee976](https://github.com/canonical/openfga-operator/commit/f5ee9767285d8ec6286b5cb7f3d530243fffd2aa))


### Bug Fixes

* Add check that dsn is there ([5fbbd1a](https://github.com/canonical/openfga-operator/commit/5fbbd1ac7c85424b895f8473c27e6c6a2ec8f5c3))
* adjust grafana dashboard sources ([d109c2d](https://github.com/canonical/openfga-operator/commit/d109c2d6bd9c70946813a804c04c4d46bd5836a1))
* bump ingress to v2 ([3c40361](https://github.com/canonical/openfga-operator/commit/3c4036140d83ab24ca83b8fb21eed617f9968a8c))
* catch error on restart ([0a7b1ad](https://github.com/canonical/openfga-operator/commit/0a7b1ad957a5b4fc6ab0492e663cece08e7c0329))
* content-type is automatically set by lib ([c28cec2](https://github.com/canonical/openfga-operator/commit/c28cec23e4d3b18fe083a2bb2a2900ffd17464ea))
* do not compute token every time ([b3b04d0](https://github.com/canonical/openfga-operator/commit/b3b04d09f04f4e1cc924df8847ffc06f04881e63))
* expose workload version ([1d7d508](https://github.com/canonical/openfga-operator/commit/1d7d5088c81edb63b73783ebe67086f9a8d0e3cc))
* fix openfga command ([36d8686](https://github.com/canonical/openfga-operator/commit/36d86860245a37f634ad44a6c73180f5c7246ff3))
* fix tests ([b785dc8](https://github.com/canonical/openfga-operator/commit/b785dc8a815dd3a99c2f9340c5d0572dc884283c))
* improve the grafana dashboard ([7896de1](https://github.com/canonical/openfga-operator/commit/7896de16d8e3efbe65fc243cbf39c9d462fae619))
* improve the grafana dashboard ([99a5c78](https://github.com/canonical/openfga-operator/commit/99a5c782fc0ca4390eb274ee03caf72c0a101a7b))
* pass log level to openfga ([5333bae](https://github.com/canonical/openfga-operator/commit/5333baeb39ef6f3f22628b1fe02fda4d79c35799))
* refactor database_created hook ([f231334](https://github.com/canonical/openfga-operator/commit/f231334c1296bcde9efb2b94b27ce6a17637bf37))
* refactor logic in _update_workload ([5e00e2f](https://github.com/canonical/openfga-operator/commit/5e00e2f9889dad00f2c9d9ce3ce834c800bed50c))
* remove duplicate check ([192273a](https://github.com/canonical/openfga-operator/commit/192273a0074a0759965ee389344254dcdcdf4196))
* remove leader requirement from db events ([eb970fc](https://github.com/canonical/openfga-operator/commit/eb970fc81349f9e91e1193f9de346ae23d4347b8))
* remove logrotate ([b11c9b8](https://github.com/canonical/openfga-operator/commit/b11c9b874ede45f3f00d02afe46db31c25fc129a))
* remove loki workaround ([9bc13b0](https://github.com/canonical/openfga-operator/commit/9bc13b036fdcd553e78ec9ec38de0f3fa421b5b7))
* remove tls integration ([839b2e6](https://github.com/canonical/openfga-operator/commit/839b2e6ea5166b9f3f21c609995964d85484249f))
* remove unused function ([f813698](https://github.com/canonical/openfga-operator/commit/f813698f9d18f46833b2ae0658767123bb12aa75))
* type annotations ([a0d20af](https://github.com/canonical/openfga-operator/commit/a0d20af5dd082a186c2f74244f56dc0ce47b454c))
* typo ([0f7bb7c](https://github.com/canonical/openfga-operator/commit/0f7bb7c3b6d57a7159415005ff20a1feefe642b8))
* unpin lightkube-models ([9ee8459](https://github.com/canonical/openfga-operator/commit/9ee8459089c4ab376a3575c93ee193d670557651))
* use ghcr image in tests ([8164b25](https://github.com/canonical/openfga-operator/commit/8164b25f507a24b2e9a82f70d6570395f7af013b))
