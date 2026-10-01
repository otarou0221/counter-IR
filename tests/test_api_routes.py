from cardboard_counter_v2.api.app import app


def test_public_api_paths_are_preserved_after_router_split() -> None:
    route_items = []
    for route in app.routes:
        nested = getattr(route, "original_router", None)
        route_items.extend(nested.routes if nested is not None else [route])
    routes = {
        (method, route.path)
        for route in route_items
        for method in getattr(route, "methods", set())
    }
    expected = {
        ("GET", "/api/health"),
        ("GET", "/api/config"),
        ("PUT", "/api/config"),
        ("GET", "/api/status"),
        ("GET", "/api/dashboard"),
        ("POST", "/api/dashboard/maps"),
        ("DELETE", "/api/dashboard/maps/{factory_map_id}"),
        ("GET", "/api/dashboard/maps/{factory_map_id}/image"),
        ("PUT", "/api/dashboard/maps/{factory_map_id}/placements"),
        ("GET", "/api/cameras/{camera_id}/stream/status"),
        ("POST", "/api/cameras/{camera_id}/calibration"),
        ("GET", "/api/roi-references"),
        ("POST", "/api/roi-references/capture"),
        ("POST", "/api/roi-references/select-floor"),
        ("GET", "/api/monitor"),
        ("POST", "/api/monitor/start"),
        ("POST", "/api/monitor/stop"),
        ("GET", "/api/debug/catalog"),
        ("POST", "/api/debug/replay"),
        ("POST", "/api/debug/capture-current"),
    }
    assert expected <= routes
    assert ("POST", "/api/calibration/run") not in routes
    assert ("POST", "/api/measure") not in routes
