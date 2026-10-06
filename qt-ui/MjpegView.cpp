#include "MjpegView.h"

#include <QNetworkReply>
#include <QNetworkRequest>
#include <QPainter>
#include <QDebug>

static const int kMaxBuffer = 8 * 1024 * 1024;

MjpegView::MjpegView(QQuickItem *parent)
    : QQuickPaintedItem(parent)
{
    setRenderTarget(QQuickPaintedItem::FramebufferObject);
    m_retry.setSingleShot(true);
    m_retry.setInterval(1000);
    connect(&m_retry, &QTimer::timeout, this, &MjpegView::open);
}

void MjpegView::setSource(const QUrl &url)
{
    if (m_source == url)
        return;
    m_source = url;
    emit sourceChanged();
    if (m_reply) {
        m_reply->abort();
    } else {
        open();
    }
}

void MjpegView::open()
{
    if (m_source.isEmpty())
        return;
    m_buffer.clear();
    QNetworkRequest req(m_source);
    req.setAttribute(QNetworkRequest::CacheLoadControlAttribute, QNetworkRequest::AlwaysNetwork);
    m_reply = m_nam.get(req);
    connect(m_reply, &QNetworkReply::readyRead, this, &MjpegView::onReadyRead);
    connect(m_reply, &QNetworkReply::finished, this, &MjpegView::onFinished);
}

void MjpegView::onReadyRead()
{
    m_buffer.append(m_reply->readAll());
    consumeBuffer();
    if (m_buffer.size() > kMaxBuffer)
        m_buffer.clear();
}

void MjpegView::consumeBuffer()
{
    // Each part: "--frame\r\nContent-Type: image/jpeg\r\nContent-Length: N\r\n\r\n<jpeg>\r\n"
    for (;;) {
        const int headerEnd = m_buffer.indexOf("\r\n\r\n");
        if (headerEnd < 0)
            return;
        const QByteArray header = m_buffer.left(headerEnd).toLower();
        int length = -1;
        const int clPos = header.indexOf("content-length:");
        if (clPos >= 0) {
            const int lineEnd = header.indexOf("\r\n", clPos);
            length = header.mid(clPos + 15, (lineEnd < 0 ? header.size() : lineEnd) - clPos - 15).trimmed().toInt();
        }
        const int dataStart = headerEnd + 4;
        if (length < 0) {
            // No length: look for the start of the next boundary after the data.
            const int next = m_buffer.indexOf("\r\n--", dataStart);
            if (next < 0)
                return;
            length = next - dataStart;
        }
        if (m_buffer.size() < dataStart + length)
            return;
        const QByteArray jpeg = m_buffer.mid(dataStart, length);
        m_buffer.remove(0, dataStart + length);
        QImage img = QImage::fromData(jpeg, "JPEG");
        if (!img.isNull()) {
            const bool first = m_frame.isNull();
            m_frame = img.convertToFormat(QImage::Format_RGB32);
            if (first)
                emit hasFrameChanged();
            update();
        }
    }
}

void MjpegView::onFinished()
{
    if (m_reply) {
        if (m_reply->error() != QNetworkReply::NoError)
            qWarning() << "preview stream:" << m_reply->errorString();
        m_reply->deleteLater();
        m_reply = nullptr;
    }
    m_retry.start();
}

void MjpegView::paint(QPainter *painter)
{
    if (m_frame.isNull())
        return;
    const QRectF target = boundingRect();
    const qreal scale = qMax(target.width() / m_frame.width(), target.height() / m_frame.height());
    const QSizeF size(m_frame.width() * scale, m_frame.height() * scale);
    const QRectF dest(target.center().x() - size.width() / 2, target.center().y() - size.height() / 2,
                      size.width(), size.height());
    painter->setRenderHint(QPainter::SmoothPixmapTransform);
    painter->drawImage(dest, m_frame);
}
