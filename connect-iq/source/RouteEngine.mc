import Toybox.Application;
import Toybox.Lang;
import Toybox.WatchUi;
using Toybox.Math;

class RoutePoint {
    var id as String;
    var lat as Float;
    var lon as Float;
    var name as String;

    function initialize(pointId as String, pointData as Dictionary) {
        id = pointId;
        lat = pointData.get("lat") as Float;
        lon = pointData.get("lon") as Float;
        name = pointData.get("name") as String;
    }
}

class RouteEngine {
    const DEFAULT_ARRIVAL_RADIUS_M = 20;
    const DEFAULT_DWELL_SEC = 4;
    const DEFAULT_START_MISMATCH_M = 50.0;

    var routeId as String = "";
    var guidanceMode as String = "point_proximity";
    var arrivalRadiusM as Number = DEFAULT_ARRIVAL_RADIUS_M;
    var dwellSec as Number = DEFAULT_DWELL_SEC;
    var orderMode as String = "fixed";
    var order as Array = [];
    var activeIndex as Number = 0;
    var taken as Array = [];
    var pointsById as Dictionary = {};
    var lapCount as Number = 0;

    var hasPlannedStart as Boolean = false;
    var plannedStartLat as Float = 0.0;
    var plannedStartLon as Float = 0.0;

    var sessionStartCaptured as Boolean = false;
    var sessionStartLat as Float = 0.0;
    var sessionStartLon as Float = 0.0;
    var startMismatchM as Float = 0.0;
    var initialDistToActiveM as Float = 0.0;

    var dwellStartedAt as Number? = null;
    var dwellProgressSec as Number = 0;

    var loaded as Boolean = false;
    var finished as Boolean = false;

    var startMismatchThresholdM as Float = DEFAULT_START_MISMATCH_M;

    function initialize() {
        loadStartMismatchThreshold();
        loadRoute();
    }

    // Маршрут берём из Storage (скачан с портала), иначе из вшитого ресурса.
    function loadRoute() as Void {
        var stored = Application.Storage.getValue("activeRoute");
        if (stored != null && stored instanceof Dictionary) {
            applyRouteDict(stored as Dictionary);
            return;
        }
        var route = WatchUi.loadResource(Rez.JsonData.Route) as Dictionary;
        if (route != null) {
            applyRouteDict(route);
        }
    }

    function loadStartMismatchThreshold() as Void {
        var value = Application.Properties.getValue("hapticStartMismatchM");
        if (value != null) {
            if (value instanceof Float) {
                startMismatchThresholdM = value as Float;
            } else if (value instanceof Number) {
                startMismatchThresholdM = (value as Number).toFloat();
            }
        }
    }

    function applyRouteDict(route as Dictionary) as Void {
        if (route == null) {
            return;
        }

        routeId = route.get("routeId") as String;
        guidanceMode = route.get("guidanceMode") as String;
        arrivalRadiusM = route.get("arrivalRadiusM") as Number;
        dwellSec = route.get("dwellSec") as Number;
        pointsById = route.get("points") as Dictionary;

        var startData = route.get("start") as Dictionary;
        if (startData != null) {
            hasPlannedStart = true;
            plannedStartLat = startData.get("lat") as Float;
            plannedStartLon = startData.get("lon") as Float;
        } else {
            hasPlannedStart = false;
        }

        var session = route.get("session") as Dictionary;
        orderMode = session.get("orderMode") as String;
        order = copyOrder(session.get("order") as Array);
        activeIndex = session.get("activeIndex") as Number;
        taken = copyOrder(session.get("taken") as Array);

        applyOrderModeOnStart();
        loaded = order.size() > 0;
        finished = activeIndex >= order.size();
    }

    function copyOrder(source as Array?) as Array {
        var result = [] as Array;
        if (source == null) {
            return result;
        }
        for (var i = 0; i < source.size(); i += 1) {
            result.add(source[i] as String);
        }
        return result;
    }

    function applyOrderModeOnStart() as Void {
        if (orderMode.equals("random")) {
            shuffleOrder();
        } else if (orderMode.equals("shuffle_each_lap")) {
            shuffleOrder();
        }
        activeIndex = 0;
        taken = [] as Array;
        finished = order.size() == 0;
        resetSessionStart();
    }

    function resetSessionStart() as Void {
        sessionStartCaptured = false;
        sessionStartLat = 0.0;
        sessionStartLon = 0.0;
        startMismatchM = 0.0;
        initialDistToActiveM = 0.0;
    }

    function shuffleOrder() as Void {
        for (var i = order.size() - 1; i > 0; i -= 1) {
            var j = Math.rand() % (i + 1);
            var tmp = order[i];
            order[i] = order[j];
            order[j] = tmp;
        }
    }

    function getActivePointId() as String? {
        if (!loaded || finished || activeIndex >= order.size()) {
            return null;
        }
        return order[activeIndex] as String;
    }

    function getActivePoint() as RoutePoint? {
        var pointId = getActivePointId();
        if (pointId == null) {
            return null;
        }
        var pointData = pointsById.get(pointId) as Dictionary;
        if (pointData == null) {
            return null;
        }
        return new RoutePoint(pointId, pointData);
    }

    function getActivePointName() as String? {
        var point = getActivePoint();
        if (point == null) {
            return null;
        }
        return point.name;
    }

    function distanceToActiveM(lat as Float, lon as Float) as Float? {
        var point = getActivePoint();
        if (point == null) {
            return null;
        }
        return GeoUtils.haversineDistanceM(lat, lon, point.lat, point.lon);
    }

    function bearingToActiveDegrees(lat as Float, lon as Float) as Float? {
        var point = getActivePoint();
        if (point == null) {
            return null;
        }
        return GeoUtils.bearingDegrees(lat, lon, point.lat, point.lon);
    }

    function captureSessionStart(lat as Float, lon as Float) as Void {
        if (sessionStartCaptured || !loaded || finished) {
            return;
        }

        sessionStartCaptured = true;
        sessionStartLat = lat;
        sessionStartLon = lon;

        if (hasPlannedStart) {
            startMismatchM = GeoUtils.haversineDistanceM(
                lat, lon, plannedStartLat, plannedStartLon
            );
        } else {
            startMismatchM = 0.0;
        }

        var dist = distanceToActiveM(lat, lon);
        initialDistToActiveM = dist != null ? dist : 0.0;
    }

    function isLegToFirstBuoy() as Boolean {
        if (!loaded || finished || order.size() == 0) {
            return false;
        }
        var firstId = order[0] as String;
        return activeIndex == 0 && !takenHas(firstId);
    }

    function isStartAnchorActive() as Boolean {
        if (!hasPlannedStart || !isLegToFirstBuoy()) {
            return false;
        }
        return startMismatchM > startMismatchThresholdM;
    }

    function takenHas(pointId as String) as Boolean {
        for (var i = 0; i < taken.size(); i += 1) {
            if ((taken[i] as String).equals(pointId)) {
                return true;
            }
        }
        return false;
    }

    function updateProximity(lat as Float, lon as Float, nowSec as Number) as Void {
        if (!loaded || finished) {
            return;
        }

        captureSessionStart(lat, lon);

        var distance = distanceToActiveM(lat, lon);
        if (distance == null) {
            resetDwell();
            return;
        }

        if (distance <= arrivalRadiusM) {
            if (dwellStartedAt == null) {
                dwellStartedAt = nowSec;
            }
            dwellProgressSec = nowSec - dwellStartedAt;
            if (dwellProgressSec >= dwellSec) {
                completeActivePoint(nowSec);
            }
        } else {
            resetDwell();
        }
    }

    function resetDwell() as Void {
        dwellStartedAt = null;
        dwellProgressSec = 0;
    }

    function completeActivePoint(nowSec as Number) as Void {
        var pointId = getActivePointId();
        if (pointId == null) {
            return;
        }

        taken.add(pointId);
        activeIndex += 1;
        resetDwell();

        if (activeIndex >= order.size()) {
            lapCount += 1;
            if (orderMode.equals("shuffle_each_lap")) {
                shuffleOrder();
                activeIndex = 0;
                taken = [] as Array;
                finished = order.size() == 0;
            } else {
                finished = true;
            }
        }
    }

    function skipActiveBuoy() as Boolean {
        if (!loaded || finished) {
            return false;
        }

        var pointId = getActivePointId();
        if (pointId == null) {
            return false;
        }

        taken.add(pointId);
        activeIndex += 1;
        resetDwell();

        if (activeIndex >= order.size()) {
            finished = true;
        }
        return true;
    }

    function isInsideRadius(lat as Float, lon as Float) as Boolean {
        var distance = distanceToActiveM(lat, lon);
        return distance != null && distance <= arrivalRadiusM;
    }

    function isSessionActive() as Boolean {
        return loaded && !finished;
    }
}
