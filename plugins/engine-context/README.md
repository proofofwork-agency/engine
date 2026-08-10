# engine-context

World Plugin v2 provider for local time, scheduled time wakes, confirmed
location and optional current weather.

Configuration is environment-based:

```shell
export ENGINE_CONTEXT_DATABASE=.engine/context.sqlite3
export ENGINE_CONTEXT_LATITUDE=52.37
export ENGINE_CONTEXT_LONGITUDE=4.90
export ENGINE_CONTEXT_SHARE_LOCATION_WITH_WEATHER=1
```

Without coordinates, location and weather observations are `UNKNOWN`. The
weather provider is not called unless location sharing is explicitly enabled.
The optional macOS provider never invokes Core Location before OS permission is
confirmed. Plugin factory construction is inert; SQLite and network work begin
only on observation.

