// Minimal Jsonnet example: reusable code generates dashboard JSON.
// jsonnet --ext-str service=checkout --ext-str metric=demo_http_requests_total \
//   dashboards/reusable.jsonnet > dashboards/generated.json
local service = std.extVar('service');
local metric = std.extVar('metric');
local panel(id, title, expr, x) = {
  id: id,
  type: 'timeseries',
  title: title,
  datasource: {type: 'prometheus', uid: 'prom-demo'},
  gridPos: {h: 8, w: 12, x: x, y: 0},
  targets: [{refId: 'A', expr: expr}],
  fieldConfig: {defaults: {}, overrides: []},
};
{
  uid: 'jsonnet-demo',
  title: service + ' generated dashboard',
  schemaVersion: 39,
  panels: [
    panel(1, 'Request rate', 'sum(rate(' + metric + '[1m]))', 0),
    panel(2, '500 error rate', 'sum(rate(' + metric + '{status="500"}[1m]))', 12),
  ],
}
