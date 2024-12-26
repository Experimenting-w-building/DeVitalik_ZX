{pkgs}: {
  deps = [
    pkgs.python310
    pkgs.python310Packages.pip
    pkgs.vim
    pkgs.glibcLocales
    pkgs.libxcrypt
    pkgs.cacert
  ];
}
