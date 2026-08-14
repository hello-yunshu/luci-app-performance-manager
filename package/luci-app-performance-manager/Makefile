include $(TOPDIR)/rules.mk

PKG_NAME:=luci-app-performance-manager
PKG_VERSION:=1.0.0_rc2
PKG_RELEASE:=1
PKG_LICENSE:=GPL-3.0-only
PKG_MAINTAINER:=OpenWrt Performance Manager contributors

LUCI_TITLE:=OpenWrt 性能管理器 LuCI 界面 / LuCI support for OpenWrt Performance Manager
LUCI_DEPENDS:=+luci-base +rpcd +performance-manager +luci-i18n-base-zh-cn
LUCI_PKGARCH:=all

include $(TOPDIR)/feeds/luci/luci.mk

define Package/luci-app-performance-manager/description
 OpenWrt 性能管理器的 LuCI 界面（简体中文优先，英文为次要语言）。
 界面语言跟随 OpenWrt/LuCI 的系统语言设置自动切换。
 / LuCI interface for OpenWrt Performance Manager (Simplified Chinese first,
 / English secondary). The UI language follows the OpenWrt/LuCI system language
 / setting automatically.
endef

# call BuildPackage - OpenWrt buildroot signature
