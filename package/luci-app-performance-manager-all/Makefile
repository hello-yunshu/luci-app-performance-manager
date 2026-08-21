include $(TOPDIR)/rules.mk

PKG_NAME:=luci-app-performance-manager-all
PKG_VERSION:=1.0.0_rc11
PKG_RELEASE:=1
PKG_LICENSE:=GPL-3.0-only
PKG_MAINTAINER:=OpenWrt Performance Manager contributors
PKG_BUILD_DEPENDS:=luci-base/host

include $(INCLUDE_DIR)/package.mk

define Package/luci-app-performance-manager-all
  SECTION:=luci
  CATEGORY:=LuCI
  SUBMENU:=3. Applications
  TITLE:=OpenWrt 性能管理器全功能单包 / Performance Manager all-in-one APK
  DEPENDS:=+luci-base +rpcd +luci-i18n-base-zh-cn +ubus +uci +ucode +ucode-mod-fs +ucode-mod-ubus +ucode-mod-uci +ucode-mod-rtnl +ucode-mod-uloop +ucode-mod-socket +ucode-mod-log
  CONFLICTS:=performance-manager luci-app-performance-manager luci-i18n-performance-manager-zh-cn performance-manager-rill
  USERID:=performance-manager-rill=5666:performance-manager-rill=5666
  PKGARCH:=all
endef

define Package/luci-app-performance-manager-all/description
 一个可直接安装的 APK，物理包含 Performance Manager Core 后端、LuCI、
 rpcd ACL/menu、简体中文翻译以及仓库自有的 Rill 接入守护层。
 Rill 运行时本身仍由上游独立发布，本包不会内置或编译 Rill 二进制。
 / One installable APK containing the Core backend, LuCI UI, rpcd ACL/menu,
 / Simplified Chinese translation and repository-owned Rill integration glue.
 / The external upstream Rill runtime itself is not bundled or compiled here.
endef

define Package/luci-app-performance-manager-all/conffiles
/etc/config/performance-manager
endef

define Package/luci-app-performance-manager-all/postinst
#!/bin/sh
[ -n "$${IPKG_INSTROOT}" ] || {
	rm -f /tmp/luci-indexcache.*
	rm -rf /tmp/luci-modulecache/
	/etc/init.d/rpcd reload 2>/dev/null
	exit 0
}
endef

define Package/luci-app-performance-manager-all/prerm
#!/bin/sh
[ -n "$${IPKG_INSTROOT}" ] && exit 0
[ "$${PKG_UPGRADE:-0}" = "1" ] && exit 0
[ -x /usr/sbin/performance-manager.uc ] || exit 0
out=$$(ubus call performance-manager cleanup '{"reason":"package-remove"}' 2>/dev/null) || true
printf '%s' "$$out" | grep -q '"ok":true' && exit 0
echo "performance-manager: uninstall cleanup failed or daemon unreachable; start the service and retry removal" >&2
exit 1
endef

define Build/Compile
	$(INSTALL_DIR) $(PKG_BUILD_DIR)
	po2lmo $(CURDIR)/../luci-app-performance-manager/po/zh_Hans/performance-manager.po \
		$(PKG_BUILD_DIR)/performance-manager.zh-cn.lmo
endef

define Package/luci-app-performance-manager-all/install
	$(INSTALL_DIR) $(1)/etc/init.d $(1)/etc/config $(1)/etc/uci-defaults
	$(INSTALL_DIR) $(1)/usr/sbin $(1)/usr/share/performance-manager/profiles
	$(INSTALL_DIR) $(1)/usr/share/performance-manager/schemas $(1)/lib/upgrade/keep.d
	$(INSTALL_BIN) $(CURDIR)/../performance-manager/files/etc/init.d/performance-manager $(1)/etc/init.d/performance-manager
	$(INSTALL_CONF) $(CURDIR)/../performance-manager/files/etc/config/performance-manager $(1)/etc/config/performance-manager
	$(INSTALL_BIN) $(CURDIR)/../performance-manager/files/etc/uci-defaults/90-performance-manager $(1)/etc/uci-defaults/90-performance-manager
	$(INSTALL_BIN) $(CURDIR)/../performance-manager/files/usr/sbin/performance-manager.uc $(1)/usr/sbin/performance-manager.uc
	$(INSTALL_DATA) $(CURDIR)/../performance-manager/files/usr/share/performance-manager/contracts.uc $(1)/usr/share/performance-manager/contracts.uc
	$(CP) $(CURDIR)/../performance-manager/files/usr/share/performance-manager/profiles/* $(1)/usr/share/performance-manager/profiles/
	$(CP) $(CURDIR)/../performance-manager/files/usr/share/performance-manager/schemas/* $(1)/usr/share/performance-manager/schemas/
	$(INSTALL_DATA) $(CURDIR)/../performance-manager/files/lib/upgrade/keep.d/performance-manager $(1)/lib/upgrade/keep.d/performance-manager

	$(INSTALL_DIR) $(1)/www $(1)/usr/share/luci $(1)/usr/share/rpcd
	cp -pR $(CURDIR)/../luci-app-performance-manager/htdocs/* $(1)/www/
	cp -pR $(CURDIR)/../luci-app-performance-manager/root/usr/share/luci/* $(1)/usr/share/luci/
	cp -pR $(CURDIR)/../luci-app-performance-manager/root/usr/share/rpcd/* $(1)/usr/share/rpcd/

	$(INSTALL_DIR) $(1)/usr/lib/lua/luci/i18n
	$(INSTALL_DATA) $(PKG_BUILD_DIR)/performance-manager.zh-cn.lmo \
		$(1)/usr/lib/lua/luci/i18n/performance-manager.zh-cn.lmo
	echo "uci set luci.languages.zh_cn='简体中文 (Simplified Chinese)'; uci commit luci" \
		> $(1)/etc/uci-defaults/luci-i18n-performance-manager-zh-cn
	chmod 0755 $(1)/etc/uci-defaults/luci-i18n-performance-manager-zh-cn

	$(INSTALL_BIN) $(CURDIR)/../performance-manager-rill/files/etc/init.d/performance-manager-rill $(1)/etc/init.d/performance-manager-rill
	$(INSTALL_DATA) $(CURDIR)/../performance-manager-rill/files/lib/upgrade/keep.d/performance-manager-rill $(1)/lib/upgrade/keep.d/performance-manager-rill
endef

$(eval $(call BuildPackage,luci-app-performance-manager-all))
