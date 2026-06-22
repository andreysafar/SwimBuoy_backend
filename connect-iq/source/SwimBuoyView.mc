import Toybox.Activity;
import Toybox.ActivityRecording;
import Toybox.Application;
import Toybox.Attention;
import Toybox.Graphics;
import Toybox.Lang;
import Toybox.Position;
import Toybox.System;
import Toybox.Time;
import Toybox.Timer;
import Toybox.WatchUi;
using Toybox.Math;

class SwimBuoyView extends WatchUi.View {
    const MAX_TRACK_POINTS = 2000;

    var routeEngine as RouteEngine;
    var hapticNavigator as HapticNavigator;
    var backendClient as BackendClient;
    var lastPosition as Position.Location?;
    var lastHeading as Float?;
    var lastActivePointId as String?;
    var hasGps as Boolean = false;
    var gpsPermissionDenied as Boolean = false;
    var gpsWaitSec as Number = 0;
    var gpsStatusLine as String?;
    var pollTimer as Timer.Timer?;
    var gpsStarted as Boolean = false;
    var recordingSession as ActivityRecording.Session?;

    var trackBuffer as Array = [];
    var lastSampleSec as Number = 0;
    var didSyncOnShow as Boolean = false;
    var uploadStatus as String?;

    function initialize() {
        View.initialize();
        routeEngine = new RouteEngine();
        hapticNavigator = new HapticNavigator();
        backendClient = new BackendClient(self);
        startGps();
    }

    function onLayout(dc as Dc) as Void {
    }

    function onShow() as Void {
        startActivityRecording();
        startGps();
        hapticNavigator.loadSettings();
        if (pollTimer == null) {
            pollTimer = new Timer.Timer();
            pollTimer.start(method(:onPollPosition), 1000, true);
        }
        if (!didSyncOnShow) {
            didSyncOnShow = true;
            // Досылаем трек прошлого заплыва (если не доехал) и тянем маршрут.
            backendClient.uploadPending();
            backendClient.syncRouteIfConfigured();
        }
        applyPositionInfo(Position.getInfo());
        WatchUi.requestUpdate();
    }

    // Перезагрузка маршрута после синка с портала.
    function reloadRoute() as Void {
        routeEngine.loadRoute();
        lastActivePointId = null;
        uploadStatus = WatchUi.loadResource(Rez.Strings.RouteSynced) as String;
        WatchUi.requestUpdate();
    }

    function getSampleSec() as Number {
        var v = Application.Properties.getValue("trackSampleSec");
        if (v != null && v instanceof Number && (v as Number) > 0) {
            return v as Number;
        }
        return 3;
    }

    // Буферизуем GPS-точки заплыва для отправки на портал.
    function sampleTrack(nowSec as Number, lat as Float, lon as Float) as Void {
        if (trackBuffer.size() >= MAX_TRACK_POINTS) {
            return;
        }
        if (lastSampleSec == 0 || nowSec - lastSampleSec >= getSampleSec()) {
            trackBuffer.add({ "t" => nowSec, "lat" => lat, "lon" => lon });
            lastSampleSec = nowSec;
        }
    }

    function buildPayload() as Dictionary? {
        if (trackBuffer.size() == 0) {
            return null;
        }
        var first = trackBuffer[0] as Dictionary;
        return {
            "route_id" => routeEngine.routeId,
            "name" => "SwimBuoy",
            "recorded_at" => first.get("t"),
            "points" => trackBuffer
        };
    }

    function isPhoneConnected() as Boolean {
        return System.getDeviceSettings().phoneConnected;
    }

    // Авто-отправка трека по завершении заплыва (если включена в настройках).
    function uploadTrackIfNeeded() as Void {
        var auto = Application.Properties.getValue("autoUpload");
        if (auto != null && auto == false) {
            return;
        }
        var payload = buildPayload();
        if (payload == null) {
            return;
        }
        uploadStatus = WatchUi.loadResource(Rez.Strings.Uploading) as String;
        backendClient.queueAndUpload(payload);
    }

    // Ручная отправка трека (пункт меню «Отправить трек»).
    function manualUpload() as Void {
        if (!isPhoneConnected()) {
            uploadStatus = WatchUi.loadResource(Rez.Strings.NoConnection) as String;
            WatchUi.requestUpdate();
            return;
        }
        var payload = buildPayload();
        if (payload == null) {
            uploadStatus = WatchUi.loadResource(Rez.Strings.NoTrack) as String;
            WatchUi.requestUpdate();
            return;
        }
        uploadStatus = WatchUi.loadResource(Rez.Strings.Uploading) as String;
        backendClient.queueAndUpload(payload);
        WatchUi.requestUpdate();
    }

    function onUploadResult(ok as Boolean) as Void {
        uploadStatus = WatchUi.loadResource(
            ok ? Rez.Strings.UploadOk : Rez.Strings.UploadFail
        ) as String;
        WatchUi.requestUpdate();
    }

    function onHide() as Void {
        if (pollTimer != null) {
            pollTimer.stop();
            pollTimer = null;
        }
        stopGps();
    }

    function startActivityRecording() as Void {
        if (recordingSession != null && recordingSession.isRecording()) {
            return;
        }
        try {
            recordingSession = ActivityRecording.createSession({
                :name => "SwimBuoy",
                :sport => Activity.SPORT_SWIMMING,
                :subSport => Activity.SUB_SPORT_OPEN_WATER,
                :recordLocation => true
            });
            recordingSession.start();
        } catch (ex) {
            recordingSession = null;
        }
    }

    function finishActivityRecording(save as Boolean) as Void {
        if (recordingSession == null) {
            return;
        }
        try {
            if (recordingSession.isRecording()) {
                if (save) {
                    recordingSession.save();
                } else {
                    recordingSession.discard();
                }
            }
        } catch (ex) {
        }
        recordingSession = null;

        if (save) {
            // Отправляем трек заплыва на портал SwimBuoy.
            uploadTrackIfNeeded();
        }
    }

    function startGps() as Void {
        if (gpsStarted || gpsPermissionDenied) {
            return;
        }
        try {
            Position.enableLocationEvents(Position.LOCATION_CONTINUOUS, method(:onPosition));
            gpsStarted = true;
        } catch (ex) {
            gpsPermissionDenied = true;
        }
    }

    function stopGps() as Void {
        if (!gpsStarted) {
            return;
        }
        try {
            Position.enableLocationEvents(Position.LOCATION_DISABLE, null);
        } catch (ex) {
        }
        gpsStarted = false;
    }

    function onPollPosition() as Void {
        if (!hasGps && !gpsPermissionDenied) {
            gpsWaitSec += 1;
            if (gpsWaitSec % 20 == 0) {
                requestOneShotGps();
            }
        }
        applyPositionInfo(Position.getInfo());
    }

    function requestOneShotGps() as Void {
        try {
            Position.enableLocationEvents(Position.LOCATION_ONE_SHOT, method(:onPosition));
        } catch (ex) {
            gpsPermissionDenied = true;
        }
    }

    function onPosition(info as Position.Info) as Void {
        applyPositionInfo(info);
    }

    function applyPositionInfo(info as Position.Info?) as Void {
        if (info == null) {
            return;
        }

        updateGpsStatusLine(info);

        if (info.position == null) {
            WatchUi.requestUpdate();
            return;
        }

        lastPosition = info.position;
        hasGps = true;
        gpsWaitSec = 0;
        if (info.heading != null) {
            lastHeading = GeoUtils.toDegrees(info.heading.toFloat());
        }
        var degrees = info.position.toDegrees();
        var lat = degrees[0].toFloat();
        var lon = degrees[1].toFloat();
        var nowSec = Time.now().value();

        sampleTrack(nowSec, lat, lon);
        routeEngine.updateProximity(lat, lon, nowSec);
        updateHaptic(lat, lon, nowSec);
        WatchUi.requestUpdate();
    }

    function updateHaptic(lat as Float, lon as Float, nowSec as Number) as Void {
        var activeId = routeEngine.getActivePointId();
        var distance = routeEngine.distanceToActiveM(lat, lon);
        if (distance == null) {
            return;
        }

        if (activeId != null && !activeId.equals(lastActivePointId)) {
            hapticNavigator.resetForNewBuoy(distance, nowSec);
            lastActivePointId = activeId;
            if (routeEngine.isStartAnchorActive()) {
                hapticNavigator.setSessionAnchor(routeEngine.initialDistToActiveM);
            } else {
                hapticNavigator.clearSessionAnchor();
            }
        }

        if (routeEngine.sessionStartCaptured && routeEngine.isLegToFirstBuoy()) {
            if (routeEngine.isStartAnchorActive()) {
                hapticNavigator.setSessionAnchor(routeEngine.initialDistToActiveM);
            }
        } else if (!routeEngine.isLegToFirstBuoy()) {
            hapticNavigator.clearSessionAnchor();
        }

        hapticNavigator.update(
            nowSec,
            distance,
            routeEngine.isInsideRadius(lat, lon),
            routeEngine.isSessionActive(),
            routeEngine.isStartAnchorActive()
        );

        if (hapticNavigator.shouldPulse()) {
            triggerHapticPulse();
            hapticNavigator.clearPulse();
        }
    }

    function triggerHapticPulse() as Void {
        if (Attention has :vibrate) {
            Attention.vibrate([new Attention.VibeProfile(50, 200)]);
        }
    }

    function onSkipBuoy() as Void {
        var nowSec = Time.now().value();
        if (!routeEngine.skipActiveBuoy()) {
            return;
        }

        lastActivePointId = null;
        if (lastPosition != null) {
            var coords = lastPosition.toDegrees();
            var lat = coords[0].toFloat();
            var lon = coords[1].toFloat();
            var distance = routeEngine.distanceToActiveM(lat, lon);
            if (distance != null) {
                hapticNavigator.resetForNewBuoy(distance, nowSec);
            }
        }

        if (!routeEngine.isLegToFirstBuoy()) {
            hapticNavigator.clearSessionAnchor();
        } else if (routeEngine.isStartAnchorActive()) {
            hapticNavigator.setSessionAnchor(routeEngine.initialDistToActiveM);
        }

        WatchUi.requestUpdate();
    }

    function onUpdate(dc as Dc) as Void {
        dc.setColor(Graphics.COLOR_BLACK, Graphics.COLOR_BLACK);
        dc.clear();

        var width = dc.getWidth();
        var height = dc.getHeight();
        var centerX = width / 2;
        var centerY = height / 2;

        if (!routeEngine.loaded) {
            drawCenteredText(dc, centerY, WatchUi.loadResource(Rez.Strings.NoRoute), Graphics.FONT_MEDIUM);
            return;
        }

        if (routeEngine.finished) {
            drawCenteredText(dc, centerY, WatchUi.loadResource(Rez.Strings.AllDone), Graphics.FONT_LARGE);
            return;
        }

        if (!hasGps || lastPosition == null) {
            drawCenteredText(dc, centerY - 24, WatchUi.loadResource(Rez.Strings.WaitingGps), Graphics.FONT_MEDIUM);
            if (gpsPermissionDenied) {
                drawCenteredText(dc, centerY, WatchUi.loadResource(Rez.Strings.GpsPermission), Graphics.FONT_XTINY);
                drawCenteredText(dc, centerY + 18, WatchUi.loadResource(Rez.Strings.WaitingGpsHint2), Graphics.FONT_XTINY);
            } else {
                var statusText = gpsStatusLine;
                if (statusText == null) {
                    statusText = WatchUi.loadResource(Rez.Strings.GpsSearching) as String;
                }
                drawCenteredText(dc, centerY, statusText, Graphics.FONT_XTINY);
                drawCenteredText(dc, centerY + 18, WatchUi.loadResource(Rez.Strings.WaitingGpsHint), Graphics.FONT_XTINY);
                if (gpsWaitSec > 0) {
                    drawCenteredText(dc, centerY + 36, gpsWaitSec.toString() + " s", Graphics.FONT_XTINY);
                }
            }
            return;
        }

        var coords = lastPosition.toDegrees();
        var lat = coords[0].toFloat();
        var lon = coords[1].toFloat();
        var distance = routeEngine.distanceToActiveM(lat, lon);
        var bearing = routeEngine.bearingToActiveDegrees(lat, lon);

        if (distance == null || bearing == null) {
            drawCenteredText(dc, centerY, WatchUi.loadResource(Rez.Strings.NoRoute), Graphics.FONT_MEDIUM);
            return;
        }

        var distanceText = distance.format("%.0f");
        var metersLabel = WatchUi.loadResource(Rez.Strings.Meters) as String;
        drawCenteredText(dc, centerY - 36, distanceText, Graphics.FONT_NUMBER_HOT);
        drawCenteredText(dc, centerY + 8, metersLabel, Graphics.FONT_SMALL);

        var pointName = routeEngine.getActivePointName();
        if (pointName != null) {
            drawCenteredText(dc, 36, pointName, Graphics.FONT_TINY);
        }

        if (uploadStatus != null) {
            drawCenteredText(dc, 56, uploadStatus, Graphics.FONT_XTINY);
        }

        var relativeBearing = GeoUtils.relativeBearingDegrees(bearing, lastHeading);
        drawArrow(dc, centerX, centerY + 72, relativeBearing, routeEngine.isInsideRadius(lat, lon));

        if (routeEngine.dwellStartedAt != null && routeEngine.dwellProgressSec > 0) {
            var dwellText = routeEngine.dwellProgressSec.toString()
                + "/"
                + routeEngine.dwellSec.toString()
                + "s";
            drawCenteredText(dc, height - 28, dwellText, Graphics.FONT_XTINY);
        }
    }

    function updateGpsStatusLine(info as Position.Info) as Void {
        var accuracy = info.accuracy;
        if (accuracy == null) {
            gpsStatusLine = null;
            return;
        }
        if (accuracy == Position.QUALITY_NOT_AVAILABLE) {
            gpsStatusLine = WatchUi.loadResource(Rez.Strings.GpsSearching) as String;
        } else if (accuracy == Position.QUALITY_LAST_KNOWN) {
            gpsStatusLine = WatchUi.loadResource(Rez.Strings.GpsLastKnown) as String;
        } else {
            gpsStatusLine = null;
        }
    }

    function drawCenteredText(
        dc as Dc,
        y as Number,
        text as String,
        font as FontDefinition
    ) as Void {
        var width = dc.getWidth();
        dc.setColor(Graphics.COLOR_WHITE, Graphics.COLOR_TRANSPARENT);
        dc.drawText(width / 2, y, font, text, Graphics.TEXT_JUSTIFY_CENTER | Graphics.TEXT_JUSTIFY_VCENTER);
    }

    function drawArrow(
        dc as Dc,
        cx as Number,
        cy as Number,
        bearingDeg as Float,
        insideRadius as Boolean
    ) as Void {
        var angleRad = (bearingDeg - 90.0) * Math.PI / 180.0;
        var shaftLen = 34;
        var headLen = 14;
        var headWidth = 10;

        var tipX = cx + (shaftLen * Math.cos(angleRad)).toNumber();
        var tipY = cy + (shaftLen * Math.sin(angleRad)).toNumber();
        var baseX = cx - (headLen * Math.cos(angleRad)).toNumber();
        var baseY = cy - (headLen * Math.sin(angleRad)).toNumber();

        var leftAngle = angleRad + (Math.PI / 2.0);
        var rightAngle = angleRad - (Math.PI / 2.0);
        var leftX = baseX + (headWidth * Math.cos(leftAngle)).toNumber();
        var leftY = baseY + (headWidth * Math.sin(leftAngle)).toNumber();
        var rightX = baseX + (headWidth * Math.cos(rightAngle)).toNumber();
        var rightY = baseY + (headWidth * Math.sin(rightAngle)).toNumber();

        var color = insideRadius ? Graphics.COLOR_GREEN : Graphics.COLOR_LT_GRAY;
        dc.setColor(color, Graphics.COLOR_TRANSPARENT);
        dc.setPenWidth(4);
        dc.drawLine(cx, cy, tipX, tipY);
        dc.fillPolygon([[tipX, tipY], [leftX, leftY], [rightX, rightY]]);
    }
}
