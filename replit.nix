{ pkgs }: {
  deps = [
    pkgs.python39
    pkgs.python39Packages.pip
    pkgs.python39Packages.setuptools
    pkgs.python39Packages.wheel
    pkgs.python39Packages.tweepy
    pkgs.python39Packages.pydantic
    pkgs.python39Packages.requests
    pkgs.python39Packages.aiohttp
  ];
}
