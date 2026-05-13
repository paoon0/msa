#!/usr/bin/python
#
# Copyright 2018 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import random
from locust import FastHttpUser, TaskSet, between ,task, constant_throughput
from faker import Faker
import datetime
fake = Faker()

products = [
    '0PUK6V6EV0',
    '1YMWWN1N4O',
    '2ZYFJ3GM2N',
    '66VCHSJNUP',
    '6E92ZMYYFZ',
    '9SIQT8TOJO',
    'L9ECAV7KIM',
    'LS4PSXUNUM',
    'OLJCESPC7Z']

def index(l):
    l.client.get("/")

#def setCurrency(l):
  #  currencies = ['EUR', 'USD', 'JPY', 'CAD', 'GBP', 'TRY']
 #   l.client.post("/setCurrency",
  #      {'currency_code': random.choice(currencies)})

#def browseProduct(l):
 #   l.client.get("/product/" + random.choice(products))

#def viewCart(l):
 #   l.client.get("/cart")

def addToCart(l):
    product = random.choice(products)
    l.client.get("/product/" + product)
    l.client.post("/cart", {
        'product_id': product,
        'quantity': 1}) #RANDINT1,10を1,1に変更
    
#def empty_cart(l):
#    l.client.post('/cart/empty')

def checkout(l):
    addToCart(l)
    #current_year = 2029
    l.client.post("/cart/checkout", {
        'email': "test@test.com",
        'street_address': "Tokyo",
        'zip_code': "100000",
        'city': "Tokyo",
        'state': "Tokyo",
        'country': "Tokyo",
        'credit_card_number': "4111111111111111",
        'credit_card_expiration_month': 1,
        'credit_card_expiration_year': 2090,
        'credit_card_cvv': "100",
    })
    
#def logout(l):
 #   l.client.get('/logout')  


class UserBehavior(TaskSet):

    def on_start(self):
        index(self)

    
    tasks = [checkout]

class WebsiteUser(FastHttpUser):
    tasks = [UserBehavior]
    #1秒当たり3回のリクエストを目標に
    wait_time = constant_throughput(3)
