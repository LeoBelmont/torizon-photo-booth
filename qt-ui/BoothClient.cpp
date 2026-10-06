#include "BoothClient.h"

#include <QJsonDocument>
#include <QJsonObject>
#include <QNetworkReply>
#include <QNetworkRequest>
#include <QUrlQuery>
#include <QDebug>

BoothClient::BoothClient(const QUrl &baseUrl, int pollMs, QObject *parent)
    : QObject(parent), m_base(baseUrl), m_pollMs(pollMs)
{
    m_timer.setSingleShot(true);
    connect(&m_timer, &QTimer::timeout, this, &BoothClient::poll);
    poll();
}

QString BoothClient::photoUrl(int id, const QString &which, const QString &tag) const
{
    QUrl url = m_base.resolved(QUrl(QStringLiteral("/api/photo/%1/%2").arg(id).arg(which)));
    if (!tag.isEmpty()) {
        QUrlQuery q;
        q.addQueryItem(QStringLiteral("t"), tag);
        url.setQuery(q);
    }
    return url.toString();
}

void BoothClient::trigger(const QString &effect, bool force)
{
    QUrl url = m_base.resolved(QUrl(QStringLiteral("/api/trigger")));
    QUrlQuery q;
    if (force)
        q.addQueryItem(QStringLiteral("force"), QStringLiteral("1"));
    if (!effect.isEmpty())
        q.addQueryItem(QStringLiteral("effect"), effect);
    url.setQuery(q);
    QNetworkReply *reply = m_nam.post(QNetworkRequest(url), QByteArray());
    connect(reply, &QNetworkReply::finished, reply, &QNetworkReply::deleteLater);
}

void BoothClient::poll()
{
    if (m_inflight)
        return;
    QNetworkRequest req(m_base.resolved(QUrl(QStringLiteral("/api/state"))));
    req.setTransferTimeout(3000);
    m_inflight = m_nam.get(req);
    connect(m_inflight, &QNetworkReply::finished, this, [this] {
        QNetworkReply *reply = m_inflight;
        m_inflight = nullptr;
        reply->deleteLater();
        if (reply->error() == QNetworkReply::NoError) {
            const QJsonDocument doc = QJsonDocument::fromJson(reply->readAll());
            if (doc.isObject()) {
                m_state = doc.object().toVariantMap();
                emit stateChanged();
                setConnected(true);
            }
        } else {
            setConnected(false);
        }
        m_timer.start(m_connected ? m_pollMs : 1000);
    });
}

void BoothClient::setConnected(bool on)
{
    if (m_connected == on)
        return;
    m_connected = on;
    qInfo() << (on ? "connected to" : "lost") << m_base.toString();
    emit connectedChanged();
}
