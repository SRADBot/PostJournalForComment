#!/usr/bin/python3 -u
# -*- coding: utf-8 -*-
#
# Copyright (c) 2018 Sradbot (sradbot@yahoo.co.jp)
# Released under the MIT license
# http://opensource.org/licenses/mit-license.php
#
# shebang のオプション -u: 標準出力をバッファリングしない。
# 標準出力がコンソールでない場合は、バッファリングされるが、
# 例えば systemd から起動する場合、このために実行完了まで journal に
# 書き込まれず、途中でハングアップするとログが残らない。
#
import sys
import os
import io
import time
import re
import json
import html
import requests
from retry import retry
from datetime import datetime, timedelta
from pytz import timezone, utc
import dateutil.parser
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException as SeleniumTimeoutException
from selenium.webdriver.chrome.options import Options as ChromeOptions
from bs4 import BeautifulSoup
from pid import PidFile, PidFileError


DEFAULT_CONFIG_JSON = """
{
    "user_id": null,
    "password": null,
    "page_load_timeout": 60,
    "render_timeout": 120,
    "chrome_browser_path": "/usr/bin/chromium-browser",
    "chromedriver_path": "/usr/lib/chromium-browser/chromedriver",
    "target_id": "anonymous coward",
    "take_screenshot": false,
    "snapshot_dir": "",
    "snapshot_retention_period": "days=7",
    "login_temporarily": false,
    "local_time_zone": "Asia/Tokyo",
    "time_after": "days=1",
    "quote_length": 50,
    "dry_run": false,
    "max_post": 5,
    "take_timeout_screenshot": false,
    "next_post_inhibit_period": 60,
    "save_rss": false,
    "pid_dir": ""
}
"""

def read_config(json_io):
    for key, value in json.load(json_io).items():
        if key in CONFIG_KEY_LIST:
            exec("global {0}; {0} = value".format(key))
        else:
            raise RuntimeError("Undefined configuration key '{0}' = '{1}'".format(key, value))

CONFIG_KEY_LIST = []
for key, value in json.loads(DEFAULT_CONFIG_JSON).items():
    exec("global {0}; {0} = value".format(key))
    CONFIG_KEY_LIST.append(key)

command = sys.argv.pop(0)
for json_file in sys.argv:
    if json_file == '-':
        read_config(sys.stdin)
    else:
        with open(json_file, "r") as json_io:
            read_config(json_io)

local_time_zone = timezone(local_time_zone)
start_time = datetime.now(local_time_zone)
if pid_dir == "":
    pid_dir = snapshot_dir


pid_file = PidFile(pidname="post_journal_for_comment.py", piddir=pid_dir)
try:
    pid_file.create()
except PidFileError as error:
    print("# MULTIPLE EXECUTION; EXIT: {0}".format(error))
    exit()


def eval_timedelta(text):
    for param in re.split(r'\s*,\s*', text):
        if not re.match(r'^(days|seconds|microseconds|milliseconds|minutes|hours|weeks)\s*=\s*\d+$', param):
            return None
    return eval("timedelta({0})".format(text))


time_delta = eval_timedelta(time_after)
if isinstance(time_delta, timedelta):
    time_after = start_time - time_delta
else:
    time_after = dateutil.parser.parse(time_after)
print("# TIME_AFTER: {0}".format(time_after))

if snapshot_dir == "":
    snapshot_dir = os.getcwd()
if not os.path.isdir(snapshot_dir):
    raise RuntimeError("Directory {0} does not esxist.".format(snapshot_dir))


snapshot_retention_period = eval_timedelta(snapshot_retention_period)
snapshot_retention_time = start_time - snapshot_retention_period
print("# SNAPSHOT RETENTION: DIR: {0}; BEFORE {1}".format(snapshot_dir, snapshot_retention_time))
for entry in os.scandir(snapshot_dir):
    if not entry.is_file or not os.access(entry.path, os.W_OK):
        continue
    unix_mtime = entry.stat().st_mtime
    utc_mtime = utc.localize(datetime.utcfromtimestamp(unix_mtime))
    local_mtime = utc_mtime.astimezone(local_time_zone)
    if local_mtime >= snapshot_retention_time:
        continue
    print("### REMOVE: {0}; {1}  ".format(entry.name, local_mtime))
    if dry_run:
        continue
    os.remove(entry.path)


@retry(tries=3, delay=10, backoff=1.5)
def http_get(driver, url):
    driver.get(url)


def get_proxy_list_from_cybersyndrome_net(driver = None, timeout = 60):
    """
    Get proxy list from http://www.cybersyndrome.net/pla6.html.
    """
    quit_driver = True
    if driver is None:
        options = ChromeOptions()
        options.binary_location = chrome_browser_path
        options.add_argument('--headless')
        options.add_argument('--no-sandbox')
    
        driver = webdriver.Chrome(chromedriver_path, chrome_options = options)
    else:
        quit_driver = False
    try:
        driver.set_page_load_timeout(timeout)
        
        http_get(driver, "http://www.cybersyndrome.net/pla6.html")
        data = driver.page_source

        soup = BeautifulSoup(data, "lxml")
        return [x.string for x in soup.find("ol", style="list-style-type: none;").find_all("a")]
    finally:
        if quit_driver:
            driver.quit()


def timestamp():
    return datetime.now().strftime("%Y-%m-%d-%H-%M-%S-%f")


def do_take_screenshot(driver, tag = "TAG"):
    if take_screenshot:
        driver.save_screenshot("{0}/{1}-{2}.png".format(snapshot_dir, timestamp(), tag))


def get_rss_soup(user_id, proxy_list):
    url = "https://srad.jp/~{0}/journal/rss".format(user_id)
    while proxy_list != []:
        proxy = proxy_list[0]
        print("### TRYING TO GET {0} VIA PROXY: {1}".format(url, proxy))
        try:
            rss = requests.get(url, proxies = {"http": proxy, "https": proxy}, timeout = page_load_timeout)
            if rss.status_code != requests.codes.ok:
                print("#### ERROR: HTTP STATUS CODE {0} FOR URL {1}".format(rss.status_code, url))
                rss.raise_for_status()
                exit(1)  # 冗長?
            print("##### OK")
            return BeautifulSoup(rss.content, "lxml")

        except (requests.exceptions.ConnectionError, requests.exceptions.ProxyError, requests.exceptions.Timeout, requests.exceptions.ChunkedEncodingError) as error:
            print("##### CONTINUE: {0}".format(error))
            proxy_list.pop(0)


JAVASCRIPT_SCROLL_TO_ELEMENT_BY_CSS_SELECTOR = """
document.querySelector("{0}").scrollIntoView(true)
"""

def scroll_to(driver, css_selector):
    driver.execute_script(JAVASCRIPT_SCROLL_TO_ELEMENT_BY_CSS_SELECTOR.format(css_selector))

def scroll_to_and_click(driver, css_selector):
    scroll_to(driver, css_selector)
    driver.find_element_by_css_selector(css_selector).click()


print("# GET PROXY LIST")
proxy_list = get_proxy_list_from_cybersyndrome_net(timeout = page_load_timeout)
print("# NUMBER OF PROXIES: {0}".format(len(proxy_list)))
if len(proxy_list) < 1:
    raise RunTimeError("No proxy found.")


print("# USER RSS")
user_soup = get_rss_soup(user_id, proxy_list)

REGEX_TEXT_HEADER = re.compile(r"^\s*(?P<TIME>.*?)、{0}は".format(target_id))
for item in user_soup.find_all("item"):
    match = REGEX_TEXT_HEADER.search(item.find("description").text)
    if bool(match):
        try:
            item_time = dateutil.parser.parse(match.group("TIME"))
        except ValueError:
            continue
        if time_after < item_time:
            time_after = item_time
            break

print("### TARGET ITEMS AFTER {0} WILL BE REPOSTED".format(time_after))


print("# TARGET RSS")
target_soup = get_rss_soup(target_id, proxy_list)

post_item_list = []
for item in target_soup.find_all("item"):
    utc_time = dateutil.parser.parse(item.find("dc:date").text)
    local_time = utc_time.astimezone(local_time_zone)
    if time_after < local_time:
        item_hash = {
            "TITLE": item.find("title").text,
            "LINK": item.get("rdf:about"),
            "TIME": local_time,
            "DESCRIPTION": item.find("description").text,
        }
        post_item_list.append(item_hash)
    else:
        break

if len(post_item_list) < 1:
    print("# NO TARGET ITEM; EXIT")
    exit()


if save_rss:
    with open("{0}/{1}-RSS-{2}.xml".format(snapshot_dir, timestamp(), user_id), 'w') as f:
        f.write(user_soup.prettify())
    with open("{0}/{1}-RSS-{2}.xml".format(snapshot_dir, timestamp(), target_id), 'w') as f:
        f.write(target_soup.prettify())


if max_post > 0 and len(post_item_list) > max_post:
    print("# LIMIT TARGET ITEMS: {0} -> {1}".format(len(post_item_list), max_post))
    post_item_list = post_item_list[0:max_post]

post_item_list.reverse()


print("# TARGET ITEMS:")
item_count = 0
for item in post_item_list:
    print("### #{0}".format(item_count))
    print("TITLE:", item["TITLE"])
    print("LINK:", item["LINK"])
    print("TIME:", item["TIME"].strftime("%Y/%m/%d %H:%M:%S"))
    print("DESCRIPTION:", item["DESCRIPTION"][0:30])
    print()
    item_count += 1


item_count = 0
next_post_wait = 0
for proxy in proxy_list:
    print("### TRYING PROXY: {0}".format(proxy))

    options = ChromeOptions()
    options.binary_location = chrome_browser_path
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-gpu")
    options.add_argument("--proxy-server={0}".format(proxy))
    options.add_argument("--lang=ja")
    #options.add_argument("--blink-settings=imagesEnabled=false")

    driver = webdriver.Chrome(chromedriver_path, chrome_options = options)
    try:
        driver.set_window_size(1280, 800)
        driver.set_page_load_timeout(page_load_timeout)

        print("##### TRYING TO GET THE LOGIN PAGE")
        driver.get("https://srad.jp/my/login")

        print("##### WAITING #1")
        element = WebDriverWait(driver, render_timeout).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "#content #firehose"))
        )

        print("##### PAGE TITLE: {0}".format(driver.title))
        do_take_screenshot(driver, "my-login-page")

        if re.match(r"ログイン", driver.title):
            print("##### TRYING TO LOGIN")
            driver.find_element_by_name("unickname").send_keys(user_id)
            driver.find_element_by_name("upasswd").send_keys(password)
            if login_temporarily:
                driver.find_element_by_name("login_temp").click()

            do_take_screenshot(driver, "before-login")

            driver.find_element_by_name("userlogin").click()

            print("##### WAITING #2")
            element = WebDriverWait(driver, render_timeout).until(
                EC.text_to_be_present_in_element((By.CLASS_NAME, "user-menu-title"), user_id)
            )
            print("##### LOGGED IN")
            print("##### PAGE TITLE: {0}".format(driver.title))

        elif re.match(r"のページ", driver.title):
            print("##### ALREADY LOGGED IN")
        else:
            raise RuntimeError("Unknown page: {0}".format(driver.title))

        do_take_screenshot(driver, "after-login")


        print("##### POST JOURNALS:")
        # for でなくwhile を使うのは、ループ途中で Timeout が発生した場合に
        # 既に投稿した記事を再投稿するのを防ぐため。for の中で、ループ対象の
        # 配列の要素を削除すると、正しく動かない。
        while post_item_list != []:
            item = post_item_list[0]
            print("####### POSTING JOURNAL #{0}".format(item_count))
            print("######### TRYING TO GET THE JOURNAL POSTING PAGE")
            driver.get("https://srad.jp/journal?new")

            print("######### WAITING #3")
            element = WebDriverWait(driver, render_timeout).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "input#edit-preview-button"))
            )

            do_take_screenshot(driver, "journal-posting-{0:03d}-before-input".format(item_count))

            text = "{0}、{1}は書きました:\n".format(item["TIME"], target_id)
            text += "<blockquote>\n{0}\n</blockquote>\n".format(item["DESCRIPTION"][0:quote_length])
            text += '<a href="{0}">怒らないで続きを読む...</a>'.format(item["LINK"])
            print("######### {0} / {1}".format(item["TITLE"], text[0:60]))

            textbox_title = driver.find_element_by_name("title")
            textbox_title.clear()
            textbox_title.send_keys("Re: {0}".format(item["TITLE"]))
            driver.find_element_by_name("introtext").send_keys(text)
            driver.find_element_by_name("tag-entry-input").send_keys("変なモノ {0} ".format(target_id))

            do_take_screenshot(driver, "journal-posting-{0:03d}-after-input".format(item_count))

            print("######### PREVIEWING")
            scroll_to_and_click(driver, "input#edit-preview-button")
            driver.find_element_by_css_selector("input#edit-preview-button").click()

            print("######### WAITING #4")
            element = WebDriverWait(driver, render_timeout).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "input#edit-edit-save"))
            )

            do_take_screenshot(driver, "journal-posting-{0:03d}-previewing".format(item_count))

            if next_post_wait > 0:
                print("######### SLEEP FOR NEXT POST: {0} s".format(next_post_wait))
                time.sleep(next_post_wait)

            print("######### POSTING")
            if dry_run:
                pass
            else:
                scroll_to_and_click(driver, "input#edit-edit-save")
                element = WebDriverWait(driver, render_timeout).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "span.modal_ok"))
                )
                next_post_wait = next_post_inhibit_period

            do_take_screenshot(driver, "journal-posting-{0:03d}-after-posing".format(item_count))

            item_count += 1

            post_item_list.pop(0)

        break


    except SeleniumTimeoutException:
        print("##### TIMEOUT")
        if take_timeout_screenshot:
            print("##### PAGE TITLE: {0}".format(driver.title))
            do_take_screenshot(driver, "timeout")


    finally:
        driver.quit()
