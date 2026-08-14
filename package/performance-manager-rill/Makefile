include $(TOPDIR)/rules.mk

PKG_NAME:=performance-manager-rill
PKG_VERSION:=1.0.0-rc.2
PKG_RELEASE:=1
PKG_LICENSE:=GPL-2.0-only
PKG_MAINTAINER:=OpenWrt Performance Manager contributors
PKG_BUILD_DEPENDS:=rust/host
PKG_BUILD_DIR:=$(BUILD_DIR)/$(PKG_NAME)-$(PKG_VERSION)
RUST_PKG_LOCKED:=1

include $(INCLUDE_DIR)/package.mk
include $(TOPDIR)/feeds/packages/lang/rust/rust-package.mk

define Package/performance-manager-rill
  SECTION:=net
  CATEGORY:=Network
  SUBMENU:=Routing and Redirection
  TITLE:=Rill Shadow sidecar for OpenWrt Performance Manager
  DEPENDS:=+performance-manager
  USERID:=performance-manager-rill=5666:performance-manager-rill=5666
endef

define Package/performance-manager-rill/description
 A constrained, non-actuating Shadow sidecar. It accepts only root-authenticated
 Unix socket peers, never writes router configuration and never executes shell.
endef

define Build/Prepare
	$(call Build/Prepare/Default)
	$(CP) ./src/. $(PKG_BUILD_DIR)/
endef

define Build/Compile
	$(call Build/Compile/Cargo)
endef

define Package/performance-manager-rill/install
	$(INSTALL_DIR) $(1)/usr/sbin $(1)/etc/init.d $(1)/lib/upgrade/keep.d
	$(INSTALL_BIN) $(PKG_INSTALL_DIR)/bin/performance-manager-rill $(1)/usr/sbin/performance-manager-rill
	$(INSTALL_BIN) ./files/etc/init.d/performance-manager-rill $(1)/etc/init.d/performance-manager-rill
	$(INSTALL_DATA) ./files/lib/upgrade/keep.d/performance-manager-rill $(1)/lib/upgrade/keep.d/performance-manager-rill
endef

$(eval $(call BuildPackage,performance-manager-rill))
