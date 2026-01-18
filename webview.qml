import QtQuick 2.15
import QtQuick.Controls 2.15
import QtWebEngine

Item {
    id: root
    anchors.fill: parent

    property url initialUrl: "https://www.google.com"
    property string profilePath: (typeof webProfilePath !== 'undefined' && webProfilePath) ? webProfilePath : ""

    signal titleChangedPy(string title)
    signal urlChangedPy(string url)
    signal newWindowRequestedPy(string url)
    signal canNavigateChangedPy(bool canBack, bool canForward)

    WebEngineView {
        id: view
        anchors.fill: parent

        // This is the key: Using a named profile that persists
        // across all instances of this QML file.
        profile: WebEngineProfile {
            storageName: "AmazonEbayListerShared"
            offTheRecord: false
            httpCacheType: WebEngineProfile.DiskHttpCache
            persistentCookiesPolicy: WebEngineProfile.ForcePersistentCookies
            persistentStoragePath: root.profilePath
            cachePath: root.profilePath ? root.profilePath + "/cache" : ""
        }

        url: "about:blank"

        onTitleChanged: root.titleChangedPy(title || "")
        onUrlChanged: {
            root.urlChangedPy((view.url || "").toString())
            emitNavState()
        }
        onLoadingChanged: emitNavState()
        onLoadProgressChanged: emitNavState()

        onNewWindowRequested: function(request) {
            if (request && request.requestedUrl)
                root.newWindowRequestedPy(request.requestedUrl.toString())
        }
    }

    function emitNavState() {
        var h = view.navigationHistory
        root.canNavigateChangedPy(!!(h && h.canGoBack), !!(h && h.canGoForward))
    }

    function loadUrl(u) { try { view.url = u; } catch(e) {} }
    function goBack()   { try { view.goBack(); } catch(e) {} }
    function goForward(){ try { view.goForward(); } catch(e) {} }
    function reload()   { try { view.reload(); } catch(e) {} }
}