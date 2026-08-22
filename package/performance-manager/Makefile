include $(TOPDIR)/rules.mk

PKG_NAME:=performance-manager
PKG_VERSION:=1.0.0_rc13
PKG_RELEASE:=1
PKG_LICENSE:=GPL-3.0-only
PKG_MAINTAINER:=OpenWrt Performance Manager contributors

include $(INCLUDE_DIR)/package.mk

define Package/performance-manager
  SECTION:=net
  CATEGORY:=Network
  SUBMENU:=Routing and Redirection
  TITLE:=OpenWrt 性能管理器核心（以能力为先的性能控制平面）/ Capability-first OpenWrt performance control plane
  DEPENDS:=+ubus +uci +ucode +ucode-mod-fs +ucode-mod-ubus +ucode-mod-uci +ucode-mod-rtnl +ucode-mod-uloop +ucode-mod-socket +ucode-mod-log
endef

define Package/performance-manager/description
 以能力为先、感知拓扑并采用事务机制的 OpenWrt 性能管理器。
 核心独立于 LuCI、rpcd 和可选的 Rill Shadow 服务。
 / A topology-aware, evidence-driven and transactional performance manager.
 / Core is independent from LuCI, rpcd and the optional Rill Shadow service.
endef

define Package/performance-manager/conffiles
/etc/config/performance-manager
endef

define Package/performance-manager/prerm
#!/bin/sh
[ -n "$${IPKG_INSTROOT}" ] && exit 0
[ "$${PKG_UPGRADE:-0}" = "1" ] && exit 0
# Root-only package removal path. Core restores only the exact runtime lease it
# still owns; live drift is preserved and only replay intent is removed.
# Fail-closed: removal aborts unless the daemon itself confirms the cleanup. An
# inert replay (binary already gone) needs no cleanup and may exit 0; a stopped
# daemon, an unreachable ubus or a business-level ok:false aborts removal with
# a visible error instead of silently leaving PM-owned state behind.
[ -x /usr/sbin/performance-manager.uc ] || exit 0
out=$$(ubus call performance-manager cleanup '{"reason":"package-remove"}' 2>/dev/null) || true
printf '%s' "$$out" | grep -q '"ok":true' && exit 0
echo "performance-manager: uninstall cleanup failed or daemon unreachable; start the service and retry removal" >&2
exit 1
endef

define Build/Compile
	:
endef

define Package/performance-manager/install
	$(INSTALL_DIR) $(1)/etc/init.d $(1)/etc/config $(1)/etc/uci-defaults
	$(INSTALL_DIR) $(1)/usr/sbin $(1)/usr/share/performance-manager/profiles
	$(INSTALL_DIR) $(1)/usr/share/performance-manager/schemas $(1)/lib/upgrade/keep.d
	$(INSTALL_BIN) ./files/etc/init.d/performance-manager $(1)/etc/init.d/performance-manager
	$(INSTALL_CONF) ./files/etc/config/performance-manager $(1)/etc/config/performance-manager
	$(INSTALL_BIN) ./files/etc/uci-defaults/90-performance-manager $(1)/etc/uci-defaults/90-performance-manager
	$(INSTALL_BIN) ./files/usr/sbin/performance-manager.uc $(1)/usr/sbin/performance-manager.uc
	$(INSTALL_DATA) ./files/usr/share/performance-manager/contracts.uc $(1)/usr/share/performance-manager/contracts.uc
	$(CP) ./files/usr/share/performance-manager/profiles/* $(1)/usr/share/performance-manager/profiles/
	$(CP) ./files/usr/share/performance-manager/schemas/* $(1)/usr/share/performance-manager/schemas/
	$(INSTALL_DATA) ./files/lib/upgrade/keep.d/performance-manager $(1)/lib/upgrade/keep.d/performance-manager
endef

$(eval $(call BuildPackage,performance-manager))
