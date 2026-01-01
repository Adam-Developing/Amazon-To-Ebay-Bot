    import QtQuick 2.15
    import QtQuick.Controls 2.15
    import QtWebEngine

    Item {
        id: root
        anchors.fill: parent

        property url initialUrl: "https://www.google.com"
        // Path for persistent profile storage (cookies, cache, local storage)
        // Take value from Python context property if available; else empty
        property string profilePath: (typeof webProfilePath !== 'undefined' && webProfilePath) ? webProfilePath : ""

        signal titleChangedPy(string title)
        signal urlChangedPy(string url)
        signal newWindowRequestedPy(string url)
        signal canNavigateChangedPy(bool canBack, bool canForward)

        // Persistent WebEngine profile (shared by this view). If you want all views
        // to share one profile, instantiate this at a higher scope and pass it in.
        WebEngineProfile {
            id: persistentProfile
            // Ensure storageName is non-empty so WebEngine switches from off-the-record
            storageName: "embeddedProfile"
            offTheRecord: false
            httpCacheType: WebEngineProfile.DiskHttpCache
            persistentCookiesPolicy: WebEngineProfile.ForcePersistentCookies
            // Bindings so Python can set the storage path at runtime before navigation
            persistentStoragePath: profilePath
            cachePath: profilePath ? profilePath + "/cache" : ""
        }

        WebEngineView {
            id: view
            anchors.fill: parent
            profile: persistentProfile
            // Don't auto-navigate before Python calls loadUrl()
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

        // Guarded Connections so target isn't undefined during construction
        Connections {
            id: histConn
            target: view.navigationHistory ? view.navigationHistory : null
            ignoreUnknownSignals: true
            function onCanGoBackChanged()    { emitNavState() }
            function onCanGoForwardChanged() { emitNavState() }
        }

        // Centralised emitter for back/forward button state
        function emitNavState() {
            var h = view.navigationHistory
            root.canNavigateChangedPy(
                !!(h && h.canGoBack),
                !!(h && h.canGoForward)
            )
        }

        // Ensure initial nav state updates
        Component.onCompleted: {
            emitNavState()
        }

        // Slim loading bar
        Rectangle {
            id: topProgress
            height: 3
            anchors.top: parent.top
            anchors.left: parent.left
            color: "#4285F4"
            visible: view.loading
            width: parent.width * (Math.max(0, Math.min(100, view.loadProgress)) / 100)
            z: 10
            Behavior on width { NumberAnimation { duration: 150; easing.type: Easing.InOutQuad } }
            Behavior on visible { PropertyAnimation { duration: 120 } }
        }

        // Methods callable from Python
        function loadUrl(u) { try { view.url = u; } catch(e) {} }
        function goBack()   { try { view.goBack(); } catch(e) {} }
        function goForward(){ try { view.goForward(); } catch(e) {} }
        function reload()   { try { view.reload(); } catch(e) {} }
    }
