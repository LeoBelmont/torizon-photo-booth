import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import QtQuick.Window
import BoothPanel

// The photo booth panel: a port of the booth's web page (index.html / app.js) to Qt Quick.
Window {
    id: root
    visible: true
    visibility: Window.FullScreen
    width: 1280
    height: 720
    title: qsTr("Torizon Photo Booth")
    color: "#0d1117"

    // Palette of the original style.css
    readonly property color panel: "#161b22"
    readonly property color line: "#283040"
    readonly property color text: "#e6edf3"
    readonly property color dim: "#8b98a5"
    readonly property color accent: "#17a2b8"
    readonly property color go: "#3fb950"
    readonly property color err: "#f85149"
    readonly property int fadeIn: 700
    readonly property int fadeOut: 900
    readonly property int gap: 18

    readonly property var s: client.state
    readonly property string boothState: s.state !== undefined ? s.state : ""
    readonly property var stats: s.stats !== undefined ? s.stats : ({ photos: 0 })
    readonly property var gallery: s.gallery !== undefined ? s.gallery : []
    readonly property bool live: s.source !== undefined && s.source.live === true

    // Replay of a gallery photo (tap), held for 7 s like the web panel
    property int replayingId: -1
    property string replayLabel: ""
    Timer {
        id: replayTimer
        interval: 7000
        onTriggered: { root.replayingId = -1; root.replayLabel = "" }
    }
    function replay(id, label) {
        root.replayingId = id
        root.replayLabel = label
        replayTimer.restart()
    }
    // A new photo takes the screen and cancels a replay; a tap during the reveal of the
    // current photo wins over it (the web panel snapped back to the reveal, which read as
    // the gallery being stuck for the 14 s reveal hold).
    readonly property int photoCount: stats.photos !== undefined ? stats.photos : 0
    onPhotoCountChanged: { replayTimer.stop(); replayingId = -1; replayLabel = "" }

    // Debug aid: with BOOTH_UI_TAP_TEST_MS set, tap through the gallery automatically and
    // log the timing of each reveal load, plus the frame rate, to find stalls.
    property int frameCount: 0
    onFrameSwapped: frameCount++
    Timer {
        interval: 1000; repeat: true; running: client.tapTestMs > 0
        onTriggered: { console.log("TAPTEST fps", root.frameCount); root.frameCount = 0 }
    }
    Timer {
        id: tapStorm
        property int n: 0
        interval: client.tapTestMs; repeat: true
        running: client.tapTestMs > 0 && root.gallery.length > 0 && n < 60
        onTriggered: {
            const g = root.gallery[n % root.gallery.length]; n++
            console.log("TAPTEST tap", n, "id", g.id, Date.now())
            root.replay(g.id, g.label)
        }
    }

    readonly property bool showingReveal: boothState === "reveal" && s.has_photo === true
    readonly property bool showingPhoto: replayingId >= 0 || showingReveal
    readonly property string photoSource: replayingId >= 0
        ? client.photoUrl(replayingId, "after.jpg")
        : (showingReveal ? client.photoUrl(0, "after.png", String(photoCount)) : "")
    readonly property string caption: replayingId >= 0 ? replayLabel
                                                       : (showingReveal && s.effect !== undefined && s.effect !== null ? s.effect : "")

    RowLayout {
        anchors.fill: parent
        anchors.margins: root.gap
        spacing: root.gap

        Item { Layout.fillWidth: true }

        // ---- Stage: square, full height ------------------------------------------
        Rectangle {
            id: stage
            Layout.fillHeight: true
            Layout.preferredWidth: height
            color: "#000"
            border.color: root.line
            border.width: 1
            radius: 10
            clip: true

            MjpegView {
                id: live
                anchors.fill: parent
                anchors.margins: 1
                source: client.baseUrl + "/preview.mjpg"
            }

            // The finished photo fades in over the live view
            Image {
                id: reveal
                anchors.fill: parent
                anchors.margins: 1
                fillMode: Image.PreserveAspectCrop
                cache: false
                asynchronous: true
                source: root.photoSource
                opacity: root.showingPhoto && status === Image.Ready ? 1 : 0
                onStatusChanged: if (client.tapTestMs > 0) console.log("TAPTEST reveal status", status, Date.now(), source)
                Behavior on opacity { NumberAnimation { duration: opacity > 0 ? root.fadeOut : root.fadeIn; easing.type: Easing.InOutQuad } }
            }

            // Prompt / smile meter / working indicator
            Column {
                id: overlay
                anchors.horizontalCenter: parent.horizontalCenter
                anchors.bottom: parent.bottom
                anchors.bottomMargin: 30
                width: parent.width
                spacing: 16
                opacity: root.showingPhoto ? 0 : 1
                Behavior on opacity { NumberAnimation { duration: root.fadeOut; easing.type: Easing.InOutQuad } }

                // prompt pill
                Rectangle {
                    anchors.horizontalCenter: parent.horizontalCenter
                    visible: root.boothState !== "generate"
                    width: promptLabel.implicitWidth + 44
                    height: promptLabel.implicitHeight + 18
                    radius: height / 2
                    color: Qt.rgba(13/255, 17/255, 23/255, 0.78)
                    Label {
                        id: promptLabel
                        anchors.centerIn: parent
                        font.pixelSize: 28
                        font.bold: true
                        color: root.boothState === "error" ? root.err : root.text
                        text: {
                            if (root.boothState === "error")
                                return s.error ? s.error : qsTr("Something went wrong")
                            if (s.advice)
                                return s.advice
                            if (s.has_face === true)
                                return qsTr("Smile!")
                            return root.live ? qsTr("Step in front of the camera") : qsTr("Waiting for a face")
                        }
                    }
                }

                // smile meter
                Rectangle {
                    anchors.horizontalCenter: parent.horizontalCenter
                    visible: root.boothState !== "generate" && root.boothState !== "error" && !s.advice && s.has_face === true
                    width: stage.width * 0.62
                    height: 15
                    radius: 8
                    color: Qt.rgba(13/255, 17/255, 23/255, 0.8)
                    clip: true
                    Rectangle {
                        width: parent.width * Math.min(1, s.smile !== undefined ? s.smile : 0)
                        height: parent.height
                        color: root.go
                        Behavior on width { NumberAnimation { duration: 120 } }
                    }
                }

                // working
                Rectangle {
                    anchors.horizontalCenter: parent.horizontalCenter
                    visible: root.boothState === "generate"
                    width: workingRow.implicitWidth + 44
                    height: workingRow.implicitHeight + 18
                    radius: height / 2
                    color: Qt.rgba(13/255, 17/255, 23/255, 0.82)
                    Row {
                        id: workingRow
                        anchors.centerIn: parent
                        spacing: 14
                        BusyIndicator {
                            width: 26; height: 26
                            anchors.verticalCenter: parent.verticalCenter
                            running: root.boothState === "generate"
                            palette.dark: root.accent
                        }
                        Label {
                            anchors.verticalCenter: parent.verticalCenter
                            font.pixelSize: 22
                            font.bold: true
                            color: root.text
                            text: s.effect ? s.effect : qsTr("Working")
                        }
                    }
                }
            }

            // Caption of the shown photo
            Rectangle {
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.bottom: parent.bottom
                height: 110
                gradient: Gradient {
                    GradientStop { position: 0.0; color: "transparent" }
                    GradientStop { position: 1.0; color: Qt.rgba(13/255, 17/255, 23/255, 0.88) }
                }
                opacity: root.showingPhoto && root.caption !== "" ? 1 : 0
                Behavior on opacity { NumberAnimation { duration: root.fadeIn; easing.type: Easing.InOutQuad } }
                Label {
                    anchors.bottom: parent.bottom
                    anchors.bottomMargin: 20
                    anchors.horizontalCenter: parent.horizontalCenter
                    font.pixelSize: 36
                    font.bold: true
                    color: root.text
                    text: root.caption
                }
            }
        }

        // ---- Side panel ---------------------------------------------------------
        Rectangle {
            Layout.fillHeight: true
            Layout.preferredWidth: 430
            color: root.panel
            border.color: root.line
            border.width: 1
            radius: 10

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 18
                spacing: 12

                // Torizon and Arduino marks side by side (icons only, dark-theme colours)
                RowLayout {
                    Layout.fillWidth: true
                    Layout.topMargin: 6
                    Layout.bottomMargin: 6
                    spacing: 36
                    Item { Layout.fillWidth: true }
                    Image {
                        Layout.preferredHeight: 84
                        Layout.preferredWidth: 84 * 203 / 196
                        fillMode: Image.PreserveAspectFit
                        source: "qrc:/BoothPanel/assets/torizon-icon-dark.png"
                        sourceSize.height: 196
                    }
                    Image {
                        Layout.preferredHeight: 84 * 0.5
                        Layout.preferredWidth: 84 * 0.5 * 45 / 21
                        fillMode: Image.PreserveAspectFit
                        source: "qrc:/BoothPanel/assets/arduino-icon.png"
                        sourceSize.width: 420
                    }
                    Item { Layout.fillWidth: true }
                }

                Label {
                    text: qsTr("PHOTO BOOTH")
                    color: root.accent
                    font.pixelSize: 22
                    font.bold: true
                    font.letterSpacing: 3
                }
                Label {
                    text: qsTr("TAP A PHOTO TO SEE IT AGAIN")
                    color: root.dim
                    font.pixelSize: 12
                    font.letterSpacing: 2
                }

                GridView {
                    id: galleryView
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    cellWidth: width / 2
                    cellHeight: cellWidth
                    model: root.gallery
                    delegate: Item {
                        required property var modelData
                        width: galleryView.cellWidth
                        height: galleryView.cellHeight
                        Rectangle {
                            id: thumbFrame
                            anchors.fill: parent
                            anchors.margins: 5
                            radius: 8
                            color: "#000"
                            border.width: 2
                            border.color: root.replayingId === modelData.id ? root.go : root.line
                            scale: root.replayingId === modelData.id ? 1.03 : 1.0
                            Behavior on scale { NumberAnimation { duration: 160 } }
                            Image {
                                anchors.fill: parent
                                anchors.margins: 2
                                fillMode: Image.PreserveAspectCrop
                                asynchronous: true
                                source: client.photoUrl(modelData.id, "after.jpg")
                                sourceSize.width: 256
                            }
                            TapHandler { onTapped: root.replay(modelData.id, modelData.label) }
                        }
                    }
                }

                Rectangle { Layout.fillWidth: true; height: 1; color: root.line }

                RowLayout {
                    Layout.fillWidth: true
                    Label {
                        text: "<b style='color:" + root.text + "'>" + root.stats.photos + "</b> " + qsTr("photos")
                        textFormat: Text.RichText
                        color: root.dim
                        font.pixelSize: 15
                    }
                    Item { Layout.fillWidth: true }
                    Label {
                        text: s.device === "npu" ? qsTr("face swap on the Hexagon NPU")
                            : (s.device === "warming" ? qsTr("warming up the NPU…") : (s.device ? qsTr("face swap on the %1").arg(String(s.device).toUpperCase()) : ""))
                        color: root.dim
                        font.pixelSize: 13
                    }
                }
                Label {
                    text: qsTr("on-device · never uploaded")
                    color: root.go
                    font.pixelSize: 14
                    font.bold: true
                }
                Label {
                    visible: !client.connected
                    text: qsTr("Connecting to %1 …").arg(client.baseUrl)
                    color: root.err
                    font.pixelSize: 13
                }
            }
        }

        Item { Layout.fillWidth: true }
    }
}
