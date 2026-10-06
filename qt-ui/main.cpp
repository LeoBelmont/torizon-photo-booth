#include <QGuiApplication>
#include <QQmlApplicationEngine>
#include <QQmlContext>

#include "BoothClient.h"

int main(int argc, char *argv[])
{
    QGuiApplication app(argc, argv);

    // The booth backend is the "booth" service of the compose project.
    const QUrl boothUrl(qEnvironmentVariable("BOOTH_URL", QStringLiteral("http://booth:8080")));
    BoothClient client(boothUrl);

    QQmlApplicationEngine engine;
    engine.rootContext()->setContextProperty("client", &client);

    const QUrl url(QStringLiteral("qrc:/BoothPanel/qml/Main.qml"));
    QObject::connect(&engine, &QQmlApplicationEngine::objectCreated, &app,
                     [url](QObject *obj, const QUrl &objUrl) {
                         if (!obj && url == objUrl)
                             QCoreApplication::exit(-1);
                     }, Qt::QueuedConnection);
    engine.load(url);

    return app.exec();
}
