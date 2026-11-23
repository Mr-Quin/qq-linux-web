# Empty unless the build is given --build-context qq-deb=DIR holding a
# linuxqq.deb, as scripts/fetch-qq.sh prepares. Otherwise QQ_URL is downloaded.
FROM scratch AS qq-deb

FROM jlesage/baseimage-gui:ubuntu-24.04-v4.14.0

ARG QQ_URL=https://qqdl.gtimg.cn/qqfile/QQNT/9.9.37/beta/816b3c79/linuxqq_3.2.35-54395_amd64.deb
ARG QQ_SHA512=c1dc085f2b50702a7c408aa6b89754ea5588c0646cf259fdf5c34a63f9883e0617008d6503469e6ae25e85bd1fd4063b56d8479dcd86529587c21a7f7316e95c

LABEL org.opencontainers.image.title="qq-linux-web" \
      org.opencontainers.image.description="Official Linux QQ in the browser, with notification forwarding" \
      org.opencontainers.image.source="https://github.com/Mr-Quin/qq-linux-web" \
      qq.url=$QQ_URL

RUN --mount=type=bind,from=qq-deb,target=/qq-deb \
    add-pkg curl ca-certificates \
    && if [ -f /qq-deb/linuxqq.deb ]; then cp /qq-deb/linuxqq.deb /tmp/linuxqq.deb; \
       else curl -fsSL --retry 5 --retry-all-errors --connect-timeout 30 -o /tmp/linuxqq.deb "$QQ_URL"; fi \
    && echo "$QQ_SHA512  /tmp/linuxqq.deb" | sha512sum -c - \
    && add-pkg /tmp/linuxqq.deb fonts-noto-cjk libgbm1 libasound2t64 libnotify4 python3-dbus python3-gi apprise xdotool x11-utils \
    && rm /tmp/linuxqq.deb \
    && install_app_icon.sh file:///usr/share/icons/hicolor/512x512/apps/qq.png \
    && set-cont-env APP_NAME "QQ" \
    && set-cont-env APP_VERSION "$(dpkg-query -W -f='${Version}' linuxqq)"

COPY --chmod=755 startapp.sh /startapp.sh
COPY src/qq_notify_forward /opt/qq-notify-forward/qq_notify_forward
COPY rootfs/ /

# The settings page sits inside the base image's server block so that its
# login covers the page too.
RUN sed -i 's|^\(\s*\)include /var/tmp/nginx/term\[\.\]conf;|&\n\1include /etc/nginx-qq/notify.conf;|' \
        /opt/base/etc/nginx/default_site.conf \
    && grep -q 'include /etc/nginx-qq/notify.conf;' /opt/base/etc/nginx/default_site.conf

# Without WEB_NOTIFICATION nothing accepts QQ's desktop notifications, and the
# base image only allows it over its own HTTPS.
ENV SECURE_CONNECTION=1 \
    WEB_NOTIFICATION=1 \
    KEEP_APP_RUNNING=1

EXPOSE 5800
