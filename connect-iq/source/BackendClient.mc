import Toybox.Application;
import Toybox.Communications;
import Toybox.Lang;
import Toybox.WatchUi;
using Toybox.Time;

// Клиент портала SwimBuoy (swimbuy.iron-siber.ru).
//
//  - syncRoute():   GET /api/watch/routes/{id} -> кэш в Storage("activeRoute").
//  - uploadTrack(): POST /api/watch/activities  (буфер GPS-точек заплыва).
//
// Сетевой запрос асинхронный (Communications.makeWebRequest). Чтобы трек не
// терялся, если приложение закрылось до ответа, полезная нагрузка пишется в
// Storage("pendingUpload") и переотправляется при следующем запуске.
class BackendClient {
    var view as SwimBuoyView?;

    function initialize(swimView as SwimBuoyView?) {
        view = swimView;
    }

    function getBackendUrl() as String {
        var url = Application.Properties.getValue("backendUrl");
        if (url == null || !(url instanceof String) || (url as String).length() == 0) {
            return "https://swimbuy.iron-siber.ru";
        }
        return url as String;
    }

    function getToken() as String? {
        var t = Application.Properties.getValue("athleteToken");
        if (t == null || !(t instanceof String) || (t as String).length() == 0) {
            return null;
        }
        return t as String;
    }

    function authHeaders() as Dictionary {
        var token = getToken();
        var headers = {} as Dictionary;
        if (token != null) {
            headers.put("X-Athlete-Token", token);
        }
        return headers;
    }

    // --- Синк маршрута с портала ---

    function syncRouteIfConfigured() as Void {
        var routeId = Application.Properties.getValue("syncRouteId");
        if (routeId == null || !(routeId instanceof String) || (routeId as String).length() == 0) {
            return;
        }
        if (getToken() == null) {
            return;
        }
        var url = getBackendUrl() + "/api/watch/routes/" + (routeId as String);
        var options = {
            :method => Communications.HTTP_REQUEST_METHOD_GET,
            :headers => authHeaders(),
            :responseType => Communications.HTTP_RESPONSE_CONTENT_TYPE_JSON
        };
        Communications.makeWebRequest(url, null, options, method(:onRouteResponse));
    }

    function onRouteResponse(responseCode as Number, data as Dictionary?) as Void {
        if (responseCode == 200 && data != null && data instanceof Dictionary) {
            Application.Storage.setValue("activeRoute", data as Dictionary);
            if (view != null) {
                view.reloadRoute();
            }
        }
    }

    // --- Отправка трека заплыва ---

    // payload: { "route_id", "name", "recorded_at", "points" => [ {t,lat,lon}, ... ] }
    function queueAndUpload(payload as Dictionary) as Void {
        Application.Storage.setValue("pendingUpload", payload);
        uploadPending();
    }

    function uploadPending() as Void {
        var payload = Application.Storage.getValue("pendingUpload");
        if (payload == null || !(payload instanceof Dictionary)) {
            return;
        }
        if (getToken() == null) {
            return;
        }
        var url = getBackendUrl() + "/api/watch/activities";
        var headers = authHeaders();
        headers.put("Content-Type", Communications.REQUEST_CONTENT_TYPE_JSON);
        var options = {
            :method => Communications.HTTP_REQUEST_METHOD_POST,
            :headers => headers,
            :responseType => Communications.HTTP_RESPONSE_CONTENT_TYPE_JSON
        };
        Communications.makeWebRequest(url, payload as Dictionary, options, method(:onUploadResponse));
    }

    function onUploadResponse(responseCode as Number, data as Dictionary?) as Void {
        var ok = (responseCode == 200);
        if (ok) {
            Application.Storage.deleteValue("pendingUpload");
        }
        if (view != null) {
            view.onUploadResult(ok);
        }
    }
}
