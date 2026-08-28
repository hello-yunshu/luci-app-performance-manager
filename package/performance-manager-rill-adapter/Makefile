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
  TITLE:=PM Rill compatibility bridge (temporary target binary)
  DEPENDS:=+libc
endef

define Package/performance-manager-rill-adapter/description
 Temporary PM compatibility bridge for pm-rill-shadow v1. It is target
 specific and remains only until the generic rill-runtime IPC v3 contract is
 promoted for PM Stable. It must not be described or packaged as the Runtime.
endef

define Build/Compile
	@test -x ./files/usr/sbin/performance-manager-rill-adapter
endef

define Package/performance-manager-rill-adapter/install
	$(INSTALL_DIR) $(1)/usr/sbin
	$(INSTALL_BIN) ./files/usr/sbin/performance-manager-rill-adapter $(1)/usr/sbin/performance-manager-rill-adapter
endef

$(eval $(call BuildPackage,performance-manager-rill-adapter))
