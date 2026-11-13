include $(TOPDIR)/rules.mk

PKG_NAME:=luci-app-performance-manager
PKG_VERSION:=1.0.5
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

include $(TOPDIR)/feeds/luci/luci.mk

# call BuildPackage - OpenWrt buildroot signature
