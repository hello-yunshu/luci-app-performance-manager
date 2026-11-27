include $(TOPDIR)/rules.mk

PKG_NAME:=performance-manager-rill
# Source checkouts and SDK staging place VERSION at different depths.
PM_PACKAGE_DIR:=$(dir $(realpath $(lastword $(MAKEFILE_LIST))))
PM_VERSION_FILE:=$(firstword $(wildcard $(PM_PACKAGE_DIR)VERSION $(PM_PACKAGE_DIR)../VERSION $(PM_PACKAGE_DIR)../../VERSION $(TOPDIR)/package/openwrt-performance-manager/VERSION $(TOPDIR)/package/performance-manager-local/VERSION))
PKG_VERSION:=$(shell sed -E 's/-rc\./_rc/' "$(or $(PM_VERSION_FILE),$(error Missing PM VERSION beside the packages))")
PKG_RELEASE:=1
PKG_LICENSE:=GPL-3.0-only
PKG_MAINTAINER:=OpenWrt Performance Manager contributors

# This package is PM's integration glue. The generic Runtime is supplied by
# the external rill-openwrt-packages feed.

include $(INCLUDE_DIR)/package.mk

define Package/performance-manager-rill
  SECTION:=net
  CATEGORY:=Network
  SUBMENU:=Routing and Redirection
  TITLE:=OpenWrt 性能管理器 Rill 集成层 / PM Rill integration glue
  # The shared Stable Runtime package is the canonical provider for PM/CFI.
  DEPENDS:=+performance-manager +rill-runtime
  PKGARCH:=all
  USERID:=performance-manager-rill=5666:performance-manager-rill=5666
endef

define Package/performance-manager-rill/description
 PM integration glue and sysupgrade keep rule. The generic rill-runtime
 package owns /usr/bin/rill-runtime and is consumed through package
 dependency resolution. PM does not ship a private Runtime or daemon.
 / PM 集成 glue 与升级保留规则；通用 rill-runtime 包拥有
 /usr/bin/rill-runtime，PM 通过包依赖消费，不发布私有 Runtime 或 daemon。
endef

define Build/Compile
	:
endef

define Package/performance-manager-rill/install
	$(INSTALL_DIR) $(1)/lib/upgrade/keep.d
	$(INSTALL_DATA) ./files/lib/upgrade/keep.d/performance-manager-rill $(1)/lib/upgrade/keep.d/performance-manager-rill
endef

$(eval $(call BuildPackage,performance-manager-rill))
