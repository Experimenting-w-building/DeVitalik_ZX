{ pkgs }: {
  deps = [
    (pkgs.python39.withPackages (ps: [
      ps.pydantic
      ps.tweepy
      ps.openai
      ps.prompt-toolkit
      ps.anthropic
    ]))
  ];
}
