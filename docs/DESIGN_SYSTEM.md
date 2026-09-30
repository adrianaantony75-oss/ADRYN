# Workspace design

The primary experience is a working command center, followed by investigation views. Business intelligence and trust operations are separate navigation groups inside the same ADRYN product. Customer IDs connect the views.

- Charcoal surfaces (#111315), a graphite sidebar (#171a1e), raised metric surfaces (#1b1e22) and cool-gray text.
- Silver navigation and primary actions; muted teal, coral and lilac for analytical distinctions only.
- Six-pixel surface corners; full-width sections and charts; compact 30px page headings.
- One meaningful unit per chart axis. Currency, population and snapshot are explicit.
- Filtered counts and exports refer to the same rows. Global forecasts and experiments display their scope.
- Hover details, table selection and Customer 360 carry the investigation from aggregate to record.
- Metric definitions use tooltips. Uncertainty and synthetic-data disclosures appear where they affect interpretation.
- A short entrance transition respects reduced-motion preferences. Motion never encodes analytical value.
- Review commands save a decision and evidence; they do not trigger external customer actions.

Responsive QA must verify actual browser rendering. Application tests alone do not establish layout quality or accessibility. Keyboard focus, chart alternatives and dense table usability require continued review before shared deployment.
