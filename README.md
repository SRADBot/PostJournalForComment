# コメント専用エントリ自動投稿ボット

## 概要
スラド(https://srad.jp/)で、特定ユーザの日記投稿を引用した日記を投稿します。

Systemd の timer や cron などから定期実行することを想定しています。


### 事前に必要なもの
#### Ubuntu のパッケージ
python3 language-pack-ja chromium-browser fonts-ipafont-gothic fonts-ipafont-mincho chromium-chromedriver

#### Pip のパッケージ
pip3 install lxml beautifulsoup4 selenium retry python-dateutil pytz pid

#### 参考
```
sudo apt update
sudo apt -y upgrade
sudo apt install -y python3-pip language-pack-ja chromium-browser fonts-ipafont-gothic fonts-ipafont-mincho chromium-chromedriver
sudo -H pip3 install --upgrade pip
sudo apt remove -y python3-pip
hash -r
sudo sh -c 'cat > /etc/pip.conf' <<'EOF'
[list]
format = columns
EOF
pip3 list -o | awk 'NR>2{print $1}' | sudo -H xargs pip3 install --upgrade
sudo -H pip3 install lxml beautifulsoup4 selenium retry python-dateutil pytz pid
```

### 設定
設定ファイルを JSON 形式で記述し、コマンドライン引数としてそのファイル名を渡します。

設定項目・内容については、本体の DEFAULT_CONFIG_JSON 変数を参照してください。

### 実行
post_journal_for_comment.py [設定ファイル名]...

設定ファイル名に、「-」を指定すると、標準入力から JSON 形式の設定を読み込みます。

### 実行例
```
$ cat ../config.json
{
    "user_id": "sadakenbot",
    "password": "sadakenbot's password",
    "target_id": "sadaken",
    "take_screenshot": true
}
$ ./post_journal_for_comment.py ../config.json
```

## ライセンス
[MIT LICENSE](https://opensource.org/licenses/mit-license.php)
