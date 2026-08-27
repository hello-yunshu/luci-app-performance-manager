include $(TOPDIR)/rules.mk

PKG_NAME:=performance-manager-rill-adapter
PKG_VERSION:=1.0.3
PKG_RELEASE:=1
PKG_LICENSE:=MIT
PKG_MAINTAINER:=OpenWrt Performance Manager contributors
PKGARCH:=$(ARCH)

include $(INCLUDE_DIR)/package.mk

define Package/performance-manager-rill-adapter
  SECTION:=net
  CATEGORY:=Network
  SUBMENU:=Routing and Redirection
  TITLE:=PM-owned Rill shadow adapter (native target binary)
  DEPENDS:=+libc
endef

define Package/performance-manager-rill-adapter/description
 PM-owned native performance-manager-rill-adapter for pm-rill-shadow v1.
 The binary is built from this repository and links exact crates.io rill-ml
 1.5.3; it is target-specific and is never downloaded from RillML Release.
endef

define Build/Compile
	@test -x ./files/usr/sbin/performance-manager-rill-adapter
endef

define Package/performance-manager-rill-adapter/install
	$(INSTALL_DIR) $(1)/usr/sbin
	$(INSTALL_BIN) ./files/usr/sbin/performance-manager-rill-adapter $(1)/usr/sbin/performance-manager-rill-adapter
endef

$(eval $(call BuildPackage,performance-manager-rill-adapter))
