# Changelog

## [1.6.3](https://github.com/canonical/openfga-operator/compare/v1.6.2...v1.6.3) (2025-12-02)


### Bug Fixes

* don't check service is running in schema-upgrade action ([d32b830](https://github.com/canonical/openfga-operator/commit/d32b830276a5f3270a30c2e6d86c00b65353a38a))
* enable the read & write split in OpenFGA ([78f30ad](https://github.com/canonical/openfga-operator/commit/78f30ad6c35b8d2febc225a396691f89ffa45ffb))
* only leader unit can run the migration action ([4e05ace](https://github.com/canonical/openfga-operator/commit/4e05ace5ac62cb70ca147376f4985d5709ab3e8d))
* update juju-tf version to ~&gt; 1.0.0 ([07ecdd9](https://github.com/canonical/openfga-operator/commit/07ecdd99c37328123be4f6bcd9510aa5c5e429ad))
* update the lib public interfaces and remove unnecessary code ([8f6810f](https://github.com/canonical/openfga-operator/commit/8f6810fb48f2589236faac41ccc82bb8abcf6f38))

## [1.6.2](https://github.com/canonical/openfga-operator/compare/v1.6.1...v1.6.2) (2025-11-10)


### Bug Fixes

* upgrade tf module to use 1.0.0 syntax ([c2bb38b](https://github.com/canonical/openfga-operator/commit/c2bb38bc9e0238b16e70938ba098aee821892ae8))

## [1.6.1](https://github.com/canonical/openfga-operator/compare/v1.6.0...v1.6.1) (2025-07-24)


### Bug Fixes

* do not pass api token in the openfga integration databag ([f6d287b](https://github.com/canonical/openfga-operator/commit/f6d287b9eee40b9c13bb91e9be1efa4373a41545))
* do not pass api token in the openfga integration databag ([b6e2972](https://github.com/canonical/openfga-operator/commit/b6e2972cf030af0aea271c4cadea6451bec0d1cb))
* don't restart service if config didn't change ([a704a0a](https://github.com/canonical/openfga-operator/commit/a704a0abf633bcb2607e08ac1a32e035d1730d15))
* update charm dependent libs ([89e4401](https://github.com/canonical/openfga-operator/commit/89e4401dfc6b0146412cecede4db9f6bf13041d3))

## [1.6.0](https://github.com/canonical/openfga-operator/compare/v1.5.3...v1.6.0) (2025-06-07)


### Features

* refactor integrations ([6e69707](https://github.com/canonical/openfga-operator/commit/6e697073fb1c31685aae6447be20934443e07a7c))
* refactor openfga client and commandline ([923fd51](https://github.com/canonical/openfga-operator/commit/923fd51db86cbfab5fb971f52649f0915dc9a88c))
* refactor workload and pebble services ([56d77e0](https://github.com/canonical/openfga-operator/commit/56d77e02a53c89657b92c2265c16aa4cbf497372))
* upgrade database integration ([32d311f](https://github.com/canonical/openfga-operator/commit/32d311fe83056fe4bd108b2e420c679dfb30dff3))


### Bug Fixes

* add resource limits ([8ef8df1](https://github.com/canonical/openfga-operator/commit/8ef8df1e2afceeb153c66349248f44b7418a3cbb))
* fix the secret id ([6e65091](https://github.com/canonical/openfga-operator/commit/6e650914d7d58cad1ab01180029265016918b794))

## [1.5.3](https://github.com/canonical/openfga-operator/compare/v1.5.2...v1.5.3) (2025-05-23)


### Bug Fixes

* fix the dependency required by k8s resource patch lib ([c2b61dd](https://github.com/canonical/openfga-operator/commit/c2b61ddbe7c63fa6d43ffec7bb53e529a903e1b5))
* fix the dependency required by k8s resource patch lib ([2c54f05](https://github.com/canonical/openfga-operator/commit/2c54f058fd0f8fbc8556a5e9b0f87b36380758d3))

## [1.5.2](https://github.com/canonical/openfga-operator/compare/v1.5.1...v1.5.2) (2025-05-22)


### Bug Fixes

* fix the issue when database integration is built after openfga integration ([f7fe707](https://github.com/canonical/openfga-operator/commit/f7fe70733c629bd010fcb4ad8a55b06c3c899672))
* fix the issue when database integration is built after openfga integration ([c565b76](https://github.com/canonical/openfga-operator/commit/c565b7614abfff7cbe04e9dd3e09d496dcb56a56))

## [1.5.1](https://github.com/canonical/openfga-operator/compare/v1.5.0...v1.5.1) (2025-05-09)


### Bug Fixes

* add pod resource constraints ([9f8706a](https://github.com/canonical/openfga-operator/commit/9f8706a732c1eaa913fa879fc517ac7824df6abc))
* fix constraint ([081c68c](https://github.com/canonical/openfga-operator/commit/081c68cabfa48939db0382a1fbc2201b9b9e6602))
* fix the TIOBE analysis ([f47e67e](https://github.com/canonical/openfga-operator/commit/f47e67e63cecb490fd996f4c0f728f6ce5c40fc7))

## [1.5.0](https://github.com/canonical/openfga-operator/compare/v1.4.2...v1.5.0) (2025-04-08)


### Features

* follow the production best practice guide ([ffca37e](https://github.com/canonical/openfga-operator/commit/ffca37e4e709f8d1954320113b91daf33d1a96ff))
* follow the production best practice guide ([a580043](https://github.com/canonical/openfga-operator/commit/a5800438c35469f8c5ee9fcf8c0f142dc7bdd2f3))

## [1.4.2](https://github.com/canonical/openfga-operator/compare/v1.4.1...v1.4.2) (2025-04-03)


### Bug Fixes

* add the check before querying the container file system ([1102fa9](https://github.com/canonical/openfga-operator/commit/1102fa9cb1d6189009027399627be834188bf604))
* add the check before querying the container file system ([57c3ce6](https://github.com/canonical/openfga-operator/commit/57c3ce61b8acc1efe69176483520acfcaabe784f))

## [1.4.1](https://github.com/canonical/openfga-operator/compare/v1.4.0...v1.4.1) (2025-04-01)


### Bug Fixes

* address CVEs ([fdce924](https://github.com/canonical/openfga-operator/commit/fdce924ec35cbfd143a223e876906b3b7ab7fccd))

## [1.4.0](https://github.com/canonical/openfga-operator/compare/v1.3.1...v1.4.0) (2025-03-28)


### Features

* implement certificate transfer integration ([eb88a9a](https://github.com/canonical/openfga-operator/commit/eb88a9aa9898630cf50ea98383fe8d122093712e))

## [1.3.1](https://github.com/canonical/openfga-operator/compare/v1.3.0...v1.3.1) (2025-03-27)


### Bug Fixes

* add optional values to charmcraft ([f339cfa](https://github.com/canonical/openfga-operator/commit/f339cfae62bcf82609821301999f8856c6a2f3f2))
* use optional flags in charmcraft ([d683b29](https://github.com/canonical/openfga-operator/commit/d683b296808c4d8f15c4b0fdc5c0cebe4d63c008))

## [1.3.0](https://github.com/canonical/openfga-operator/compare/v1.2.1...v1.3.0) (2025-03-27)


### Features

* add terraform module ([237e9b8](https://github.com/canonical/openfga-operator/commit/237e9b85b4c23494bd049ddd2a103d78c3c965ed))
* add the terraform module ([f3bcea6](https://github.com/canonical/openfga-operator/commit/f3bcea6015315ffc22b9e9e979cadad5a5a231d2))
* add tls-certificates integration ([5f46194](https://github.com/canonical/openfga-operator/commit/5f46194a65db0d01cfe91774c23594562007e0a3))
* add tls-certificates integration ([67db776](https://github.com/canonical/openfga-operator/commit/67db7766212be82eb031d4565ad47e8724796f3c))


### Bug Fixes

* fix the lint ci ([b786db7](https://github.com/canonical/openfga-operator/commit/b786db745cd20ab16e27e01a27e49ed3b777aefa))

## [1.2.1](https://github.com/canonical/openfga-operator/compare/v1.2.0...v1.2.1) (2025-03-14)


### Bug Fixes

* remove the deprecated charm lib v0 to fix the charm lib release ([39bb259](https://github.com/canonical/openfga-operator/commit/39bb259096ff11497ee5515541d752415d0df91c))
* remove the deprecated charm lib v0 to fix the charm lib release workflow ([3b3006f](https://github.com/canonical/openfga-operator/commit/3b3006f393a09a222b6e83db1da9e7b44df989db))

## [1.2.0](https://github.com/canonical/openfga-operator/compare/v1.1.0...v1.2.0) (2025-03-12)


### Features

* update the openfga lib to use Pydantic v2 ([bbe971b](https://github.com/canonical/openfga-operator/commit/bbe971bf5817668d6d34d640f8e458976fcb739b))
* update the openfga lib to use Pydantic v2 ([85496af](https://github.com/canonical/openfga-operator/commit/85496afd115ea695ef4b6852088bbb30a97bc654))


### Bug Fixes

* fix the charm and tests ([7314abc](https://github.com/canonical/openfga-operator/commit/7314abc319be10f0f67c6226a10ffe749a848aba))

## [1.1.0](https://github.com/canonical/openfga-operator/compare/v1.0.0...v1.1.0) (2025-03-10)


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
