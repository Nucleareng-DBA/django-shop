# -*- coding: utf-8
from __future__ import unicode_literals

import pytest
from django.contrib.auth.models import AnonymousUser
from django.utils import six
from shop.conf import app_settings
from shop.models.cart import CartModel
from shop.models.defaults.customer import Customer
from shop.modifiers.pool import CartModifiersPool
from shop.views.cart import CartViewSet, WatchViewSet
from rest_framework.reverse import reverse

CartModifiersPool.USE_CACHE = False


@pytest.fixture(name='filled_cart')
@pytest.mark.django_db
def test_add_to_cart(commodity_factory, api_client, rf):
    # add a product to the cart
    product = commodity_factory()
    data = {'quantity': 2, 'product': product.id}
    response = api_client.post(reverse('shop:cart-list'), data)
    assert response.status_code == 201
    assert response.data['quantity'] == 2
    assert response.data['unit_price'] == six.text_type(product.unit_price)
    assert response.data['line_total'] == six.text_type(data['quantity'] * product.unit_price)

    # verify that the product is in the cart
    request = rf.get('/my-cart')
    request.session = api_client.session
    request.user = AnonymousUser()
    request.customer = Customer.objects.get_from_request(request)
    filled_cart = CartModel.objects.get_from_request(request)
    filled_cart.update(request)
    assert filled_cart.num_items == 1
    items = filled_cart.items.all()
    assert items[0].product == product
    assert items[0].quantity == 2
    assert filled_cart.subtotal == product.unit_price * data['quantity']
    return filled_cart


@pytest.mark.django_db
def test_list_cart(api_rf, filled_cart):
    request = api_rf.get('/shop/api/cart')
    request.customer = filled_cart.customer
    response = CartViewSet.as_view({'get': 'list'})(request)
    assert response.status_code == 200
    assert response.data['num_items'] == 1
    assert response.data['total_quantity'] == 2
    assert response.data['subtotal'] == six.text_type(filled_cart.subtotal)
    assert response.data['total'] == six.text_type(filled_cart.total)


@pytest.mark.django_db
def test_unowned_cart(customer_factory, api_rf, filled_cart):
    request = api_rf.get('/shop/api/cart')
    request.customer = customer_factory()
    response = CartViewSet.as_view({'get': 'list'})(request)
    assert response.data['num_items'] == 0


@pytest.mark.django_db
def test_change_quantity(api_rf, filled_cart):
    product = filled_cart.items.all()[0].product
    data = {'quantity': 3, 'product': product.id}
    request = api_rf.put('/shop/api/cart', data)
    request.customer = filled_cart.customer
    response = CartViewSet.as_view({'put': 'update'})(request, pk=product.id)
    assert response.status_code == 200
    filled_cart.refresh_from_db()
    assert filled_cart.num_items == 1
    assert filled_cart.items.all()[0].quantity == 3


@pytest.mark.django_db
def test_remove_item(api_rf, filled_cart):
    product = filled_cart.items.all()[0].product
    request = api_rf.delete('/shop/api/cart')
    request.customer = filled_cart.customer
    response = CartViewSet.as_view({'delete': 'destroy'})(request, pk=product.id)
    assert response.status_code == 200
    filled_cart.refresh_from_db()
    assert filled_cart.num_items == 0
    assert filled_cart.items.count() == 0


@pytest.fixture(name='watch_list')
@pytest.mark.django_db
def test_watch_cart_item(api_rf, filled_cart):
    product = filled_cart.items.all()[0].product
    data = {'quantity': 0, 'product': product.id}
    request = api_rf.put('/shop/api/cart', data)
    request.customer = filled_cart.customer
    response = WatchViewSet.as_view({'put': 'update'})(request, pk=product.id)
    assert response.status_code == 200
    filled_cart.refresh_from_db()
    assert filled_cart.num_items == 0
    assert filled_cart.items.all()[0].quantity == 0
    return filled_cart


@pytest.mark.django_db
def test_add_watch_item(api_rf, watch_list):
    product = watch_list.items.all()[0].product
    data = {'quantity': 1, 'product': product.id}
    request = api_rf.put('/shop/api/cart', data)
    request.customer = watch_list.customer
    response = CartViewSet.as_view({'put': 'update'})(request, pk=product.id)
    assert response.status_code == 200
    watch_list.refresh_from_db()
    assert watch_list.num_items == 1
    assert watch_list.items.all()[0].quantity == 1


@pytest.mark.django_db
def test_include_tax_modifier(api_rf, filled_cart):
    request = api_rf.get('/shop/api/cart')
    request.customer = filled_cart.customer

    response = CartViewSet.as_view({'get': 'list'})(request)
    assert response.status_code == 200
    assert response.data['subtotal'] == six.text_type(filled_cart.subtotal)
    tax_rate = 1 + app_settings.SHOP_VALUE_ADDED_TAX / 100
    assert response.data['total'] == six.text_type(filled_cart.subtotal * tax_rate)
