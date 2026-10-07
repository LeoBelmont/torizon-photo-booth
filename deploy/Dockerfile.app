# syntax=docker/dockerfile:1
# The Arduino App itself, as an image, so a board needs nothing copied onto it: the
# deployment pulls this like any other image and seeds the App directory from it.
#
# The App is unchanged by this. It is still the folder App Lab edits and
# arduino-app-cli runs; this only carries it.
FROM busybox:stable

COPY app /app-src
# Owned by the uid the App's containers run as, so the runtime can write its generated
# compose files and virtualenv into the App folder afterwards.
RUN chown -R 1000:1000 /app-src

CMD ["true"]
