import Toybox.WatchUi;
import Toybox.Lang;
import Toybox.System;

// Меню действий: пропуск буя и ручная отправка трека на портал.
class SwimBuoyMenuDelegate extends WatchUi.Menu2InputDelegate {
    var view as SwimBuoyView;

    function initialize(swimView as SwimBuoyView) {
        Menu2InputDelegate.initialize();
        view = swimView;
    }

    function onSelect(item as WatchUi.MenuItem) as Void {
        var id = item.getId();
        WatchUi.popView(WatchUi.SLIDE_IMMEDIATE);
        if (id == :skip) {
            WatchUi.pushView(
                new WatchUi.Confirmation(WatchUi.loadResource(Rez.Strings.SkipConfirm) as String),
                new SkipConfirmDelegate(view),
                WatchUi.SLIDE_IMMEDIATE
            );
        } else if (id == :send) {
            // Активно только при наличии связи; иначе manualUpload покажет статус.
            view.manualUpload();
        }
    }
}

class SkipConfirmDelegate extends WatchUi.ConfirmationDelegate {
    var view as SwimBuoyView;

    function initialize(swimView as SwimBuoyView) {
        ConfirmationDelegate.initialize();
        view = swimView;
    }

    function onResponse(response as WatchUi.Confirm) as Boolean {
        if (response == WatchUi.CONFIRM_YES) {
            view.onSkipBuoy();
        }
        WatchUi.popView(WatchUi.SLIDE_IMMEDIATE);
        return true;
    }
}

class SwimBuoyDelegate extends WatchUi.BehaviorDelegate {
    var view as SwimBuoyView;

    function initialize(swimView as SwimBuoyView) {
        BehaviorDelegate.initialize();
        view = swimView;
    }

    function onBack() as Boolean {
        view.finishActivityRecording(true);
        WatchUi.popView(WatchUi.SLIDE_RIGHT);
        return true;
    }

    function onMenu() as Boolean {
        var menu = new WatchUi.Menu2({ :title => WatchUi.loadResource(Rez.Strings.MenuTitle) as String });

        if (view.routeEngine.isSessionActive()) {
            menu.addItem(new WatchUi.MenuItem(
                WatchUi.loadResource(Rez.Strings.MenuSkip) as String,
                null, :skip, {}
            ));
        }

        var connected = view.isPhoneConnected();
        var sub = WatchUi.loadResource(
            connected ? Rez.Strings.MenuConnected : Rez.Strings.MenuNoConn
        ) as String;
        menu.addItem(new WatchUi.MenuItem(
            WatchUi.loadResource(Rez.Strings.MenuSend) as String,
            sub, :send, {}
        ));

        WatchUi.pushView(menu, new SwimBuoyMenuDelegate(view), WatchUi.SLIDE_UP);
        return true;
    }
}
