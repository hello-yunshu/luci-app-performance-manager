include $(TOPDIR)/rules.mk

PKG_NAME:=performance-manager-rill
PKG_VERSION:=1.0.3
PKG_RELEASE:=1
PKG_LICENSE:=GPL-3.0-only
PKG_MAINTAINER:=OpenWrt Performance Manager contributors

# The adapter is a temporary compatibility bridge while PM moves to the
# generic package-owned Rill Runtime. It remains separate from the all-in-one
# Core package and never owns the Runtime executable.
PKG_BUILD_DEPENDS:=

include $(INCLUDE_DIR)/package.mk

define Package/performance-manager-rill
  SECTION:=net
  CATEGORY:=Network
  SUBMENU:=Routing and Redirection
  TITLE:=OpenWrt 性能管理器 PM-owned Rill 集成层 / PM-owned Rill integration glue
  DEPENDS:=+performance-manager +performance-manager-rill-adapter
  PKGARCH:=all
  USERID:=performance-manager-rill=5666:performance-manager-rill=5666
endef

define Package/performance-manager-rill/description
 PM integration service glue and sysupgrade keep rule. The generic
 rill-runtime package owns /usr/bin/rill-runtime. The existing adapter is a
 temporary compatibility bridge and is not the Runtime implementation.
 / PM 集成服务 glue 与升级保留规则；/usr/bin/rill-runtime 由通用
 / rill-runtime 包拥有，现有 adapter 仅为临时兼容桥，不是 Runtime 实现。
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
