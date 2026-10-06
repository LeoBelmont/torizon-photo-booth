cmake_minimum_required(VERSION 3.16)
project(booth-ui LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_AUTOMOC ON)

find_package(Qt6 REQUIRED COMPONENTS Core Gui Qml Quick Network)

qt_add_executable(booth-ui
    main.cpp
    BoothClient.cpp
    BoothClient.h
    MjpegView.cpp
    MjpegView.h
)

qt_add_qml_module(booth-ui
    URI BoothPanel
    VERSION 1.0
    RESOURCE_PREFIX /
    QML_FILES
        qml/Main.qml
    RESOURCES
        assets/torizon-logo.png
        assets/torizon-logo-dark.png
        assets/torizon-icon-dark.png
        assets/arduino-icon.png
)

target_link_libraries(booth-ui PRIVATE
    Qt6::Core Qt6::Gui Qt6::Qml Qt6::Quick Qt6::Network
)

install(TARGETS booth-ui RUNTIME DESTINATION bin)
