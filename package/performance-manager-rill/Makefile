include $(TOPDIR)/rules.mk

PKG_NAME:=performance-manager-rill
PKG_VERSION:=1.0.3
PKG_RELEASE:=1
PKG_LICENSE:=GPL-3.0-only
PKG_MAINTAINER:=OpenWrt Performance Manager contributors

# The PM-owned adapter is provisioned by the companion target-specific package.
# This package contains only service glue and the sysupgrade keep rule.
PKG_BUILD_DEPENDS:=

include $(INCLUDE_DIR)/package.mk

define Package/performance-manager-rill
  SECTION:=net
  CATEGORY:=Network
  SUBMENU:=Routing and Redirection
  TITLE:=OpenWrt 性能管理器 PM-owned Rill 集成层 / PM-owned Rill integration glue
  DEPENDS:=+performance-manager +performance-manager-rill-adapter
  USERID:=performance-manager-rill=5666:performance-manager-rill=5666
endef

define Package/performance-manager-rill/description
 PM-owned Performance Manager adapter service glue and sysupgrade keep rule.
 The native adapter is shipped by performance-manager-rill-adapter for the
 target architecture; no upstream Release artifact is required.
 / PM 自有 Rill adapter 服务 glue 与升级保留规则；native adapter 由目标架构
 / 的 performance-manager-rill-adapter 包提供，不依赖上游 Release 二进制。
endef

define Build/Compile
	:
endef

define Package/performance-manager-rill/install
	$(INSTALL_DIR) $(1)/etc/init.d $(1)/lib/upgrade/keep.d
	$(INSTALL_BIN) ./files/etc/init.d/performance-manager-rill $(1)/etc/init.d/performance-manager-rill
	$(INSTALL_DATA) ./files/lib/upgrade/keep.d/performance-manager-rill $(1)/lib/upgrade/keep.d/performance-manager-rill
endef

$(eval $(call BuildPackage,performance-manager-rill))
