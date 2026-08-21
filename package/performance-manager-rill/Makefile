include $(TOPDIR)/rules.mk

PKG_NAME:=performance-manager-rill
PKG_VERSION:=1.0.0_rc11
PKG_RELEASE:=1
PKG_LICENSE:=GPL-3.0-only
PKG_MAINTAINER:=OpenWrt Performance Manager contributors

# Rill is an EXTERNAL runtime dependency.  This package never compiles or
# bundles Rill: it only carries the PM<->Rill integration glue and a guard
# that manages an upstream-provided Rill binary when one is installed.
# When no upstream Rill binary is present the integration is fail-closed and
# reported as "external dependency blocked" by the Core capability gate.
PKG_BUILD_DEPENDS:=

include $(INCLUDE_DIR)/package.mk

define Package/performance-manager-rill
  SECTION:=net
  CATEGORY:=Network
  SUBMENU:=Routing and Redirection
  TITLE:=OpenWrt 性能管理器 Rill 集成层（外部依赖）/ PM<->Rill integration glue (external dependency)
  DEPENDS:=+performance-manager
  USERID:=performance-manager-rill=5666:performance-manager-rill=5666
endef

define Package/performance-manager-rill/description
  PM<->upstream Rill integration glue. Rill is built and released by its own
  upstream repository; this package only installs the PM-side service guard
  that starts an installed upstream Rill runtime and the sysupgrade keep rule
  for Rill state. No Rill source or binary is built here.
  / Rill 由上游仓库构建与发布，本包仅安装 PM 侧服务 guard 与升级保留规则，
  / 不在本仓库编译任何 Rill 源码或二进制。
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
