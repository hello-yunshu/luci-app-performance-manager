# OpenWrt 25.12.5 x86/64 rootfs Docker image for performance-manager external evidence gates.
# Usage:
#   docker build --platform linux/amd64 -t owrt-pm-gate .
#   docker run --rm --platform linux/amd64 -v /path/to/luci-app-performance-manager:/home/pm-src:ro owrt-pm-gate /docker-entry.sh
FROM scratch
ADD rootfs/ /
ENV PATH=/usr/sbin:/usr/bin:/sbin:/bin \
    LD_LIBRARY_PATH=/lib:/usr/lib
RUN ["/bin/sh", "-c", "apk add --no-cache ucode ucode-mod-fs ucode-mod-ubus ucode-mod-uci ucode-mod-rtnl ucode-mod-uloop ucode-mod-socket ucode-mod-log ucode-mod-math jsonfilter"]
COPY docker-entry.sh /docker-entry.sh
RUN chmod +x /docker-entry.sh
ENTRYPOINT ["/docker-entry.sh"]