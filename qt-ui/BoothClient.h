#pragma once

#include <QNetworkAccessManager>
#include <QObject>
#include <QTimer>
#include <QUrl>
#include <QVariantMap>

class QNetworkReply;

// Polls the booth's /api/state (the same JSON the web panel used) and exposes it to QML.
class BoothClient : public QObject
{
    Q_OBJECT
    Q_PROPERTY(QString baseUrl READ baseUrl CONSTANT)
    Q_PROPERTY(QVariantMap state READ state NOTIFY stateChanged)
    Q_PROPERTY(bool connected READ connected NOTIFY connectedChanged)
    // Debug aid: BOOTH_UI_TAP_TEST_MS=<ms> makes the panel tap gallery photos by itself.
    Q_PROPERTY(int tapTestMs READ tapTestMs CONSTANT)

public:
    explicit BoothClient(const QUrl &baseUrl, int pollMs = 250, QObject *parent = nullptr);

    QString baseUrl() const { return m_base.toString(); }
    QVariantMap state() const { return m_state; }
    bool connected() const { return m_connected; }
    int tapTestMs() const { return qEnvironmentVariableIntValue("BOOTH_UI_TAP_TEST_MS"); }

    // http://booth:8080/api/photo/<id>/<which>[?t=<tag>]
    Q_INVOKABLE QString photoUrl(int id, const QString &which, const QString &tag = {}) const;
    Q_INVOKABLE void trigger(const QString &effect = {}, bool force = false);

signals:
    void stateChanged();
    void connectedChanged();

private:
    void poll();
    void setConnected(bool on);

    QUrl m_base;
    int m_pollMs;
    QNetworkAccessManager m_nam;
    QTimer m_timer;
    QNetworkReply *m_inflight = nullptr;
    QVariantMap m_state;
    bool m_connected = false;
};
