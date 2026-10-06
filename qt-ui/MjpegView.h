#pragma once

#include <QImage>
#include <QNetworkAccessManager>
#include <QQuickPaintedItem>
#include <QTimer>
#include <QUrl>

class QNetworkReply;

// Shows a multipart/x-mixed-replace JPEG stream (the booth's /preview.mjpg), filling the
// item like CSS object-fit: cover. Reconnects by itself when the stream drops.
class MjpegView : public QQuickPaintedItem
{
    Q_OBJECT
    QML_ELEMENT
    Q_PROPERTY(QUrl source READ source WRITE setSource NOTIFY sourceChanged)
    Q_PROPERTY(bool hasFrame READ hasFrame NOTIFY hasFrameChanged)

public:
    explicit MjpegView(QQuickItem *parent = nullptr);

    QUrl source() const { return m_source; }
    void setSource(const QUrl &url);
    bool hasFrame() const { return !m_frame.isNull(); }

    void paint(QPainter *painter) override;

signals:
    void sourceChanged();
    void hasFrameChanged();

private:
    void open();
    void onReadyRead();
    void onFinished();
    void consumeBuffer();

    QUrl m_source;
    QNetworkAccessManager m_nam;
    QNetworkReply *m_reply = nullptr;
    QTimer m_retry;
    QByteArray m_buffer;
    QImage m_frame;
};
