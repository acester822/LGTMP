(import 'mixin.libsonnet') + {
  // Config overrides
  _config+:: {

    promtail+: {
      enabled: false,
    },

  },
}
