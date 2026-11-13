include $(TOPDIR)/rules.mk

PKG_NAME:=luci-app-performance-manager
PKG_VERSION:=1.0.6
PKG_RELEASE:=1
PKG_LICENSE:=GPL-3.0-only
PKG_MAINTAINER:=OpenWrt Performance Manager contributors

LUCI_TITLE:=OpenWrt 性能管理器 LuCI 界面 / LuCI support for OpenWrt Performance Manager
LUCI_DEPENDS:=+luci-base +rpcd +performance-manager +luci-i18n-base-zh-cn
LUCI_PKGARCH:=all

define Package/luci-app-performance-manager/description
 OpenWrt 性能管理器的 LuCI 界面（简体中文优先，英文为次要语言）。
 界面语言跟随 OpenWrt/LuCI 的系统语言设置自动切换。
 / LuCI interface for OpenWrt Performance Manager (Simplified Chinese first,
 / English secondary). The UI language follows the OpenWrt/LuCI system language
 / setting automatically.
endef

define Package/luci-app-performance-manager/postinst
#!/bin/sh
[ -n "$${IPKG_INSTROOT}" ] || {
	rm -f /tmp/luci-indexcache
	rm -rf /tmp/luci-modulecache/
	killall -HUP rpcd 2>/dev/null
}
sed -i 's/@PKG_VERSION@/$(PKG_VERSION)/g' "$${IPKG_INSTROOT}/www/luci-static/resources/performance-manager/ui.js" 2>/dev/null
exit 0
endef

# Ship the zh-cn catalog in the main package instead of relying on the
# separately versioned luci-i18n-performance-manager-zh-cn package.
# The hook must be registered before luci.mk evaluates BuildPackage.
define PMBuildLmo
	mkdir -p $(PKG_BUILD_DIR)/root/usr/lib/lua/luci/i18n
	[ -x "$(STAGING_DIR_HOSTPKG)/bin/po2lmo" ] || { echo "ERROR: po2lmo not found at $(STAGING_DIR_HOSTPKG)/bin; build luci-base/host first" >&2; exit 1; }
	"$(STAGING_DIR_HOSTPKG)/bin/po2lmo" $(CURDIR)/po/zh_Hans/performance-manager.po $(PKG_BUILD_DIR)/root/usr/lib/lua/luci/i18n/performance-manager.zh-cn.lmo
endef
Hooks/Compile/Post += PMBuildLmo

include $(TOPDIR)/feeds/luci/luci.mk

# call BuildPackage - OpenWrt buildroot signature
