"""
Views for the actual coffee shops
"""
from flask import render_template, Blueprint, redirect, current_app, request, flash, url_for
from flask_security import login_required, current_user
from sqlalchemy import func, or_

from coffeeshop.server import db
from .forms import ShopForm, ReviewForm, SearchForm
from .utils import secure_filename, save_photo
from .models import Shop, Review


coffee_blueprint = Blueprint("coffee", __name__)


# public

@coffee_blueprint.route('/shop/<int:id>')
def shops(id):
    """
    Display the informatino about the shop including the reviews

    Note to get the aerage rating generated by the database (which is almost
    certainly going to be faster than doing  it in Python as a seconday step)
    we have to make a rating subquery and pull back the information from there.

    :param id: Table ID for the coffeeshop
    """
    rating_query = db.session.query(
        Review.shop_id,
        func.avg(Review.rating).label('rating')
    ).group_by(
        Review.shop_id
    ).subquery()
    query = db.session.query(
        Shop,
        rating_query.c.rating
    ).outerjoin(
        rating_query,
        Shop.id == rating_query.c.shop_id
    ).filter(Shop.id == id)
    shop, avg_rating = query.first_or_404()

    review_comments = list(filter(lambda r: r.comment, shop.reviews))
    return render_template(
        'shop/shop_details.html',
        shop=shop,
        avg_rating=avg_rating,
        review_comments=review_comments
    )


@coffee_blueprint.route('/shop/search')
def search_shop():
    """
    Search for a coffeeshop by name or address.

    A full text search could be implemented in postgresql (or MySQL or SQLite)
    but then you spend a lot of time writing platform specifc code. A better
    solution (I think) is the solution using Elasticsearch as outlined by
    Miguel Grinberg here: https://blog.miguelgrinberg.com/post/the-flask-mega-tutorial-part-xvi-full-text-search

    For our purposes we'll be super lazy and just do simple like queries
    against the name and the address field.
    """
    try:
        search_term = request.args['q']
        search_term = f'%{search_term}%'
    except KeyError:
        shops = None
    else:
        shops = db.session.query(Shop).filter(or_(
            Shop.name.ilike(search_term),
            Shop.address.ilike(search_term)
        ))

    return render_template(
        'shop/search_shops.html',
        shops=shops,
        form=SearchForm()
    )


# login required


@coffee_blueprint.route('/shop/add', methods=['GET', 'POST'])
@login_required
def add_shop():
    """
    Standard GET endpoint to get a form to enter a shop using the POST endpoint

    Follows the standard pattern of rendering the andpoint on the server side.
    Note this isn't talking to an API - this is the traditional model of
    rendering the page on the server and returning the rendered page. Note if
    you look at the template you can see the script where we grab the user's
    current location (which isn't really used anywhere yet).
    """
    form = ShopForm()
    if form.validate_on_submit():

        shop_name = form.name.data
        address = form.address.data
        url = form.url.data

        latitude = form.latitude.data
        longitude = form.longitude.data
        current_app.logger.debug(f'{latitude} {longitude}')

        photo = None
        f = form.photo.data
        if f:
            f.filename = secure_filename(f.filename)
            photo = save_photo(f)

        shop = Shop(
            name=shop_name,
            address=address,
            url=url,
            photo=photo,
            latitude=float(latitude),
            longitude=float(longitude),
            user=current_user
        )
        db.session.add(shop)
        db.session.commit()
        current_app.logger.info(f'Created new {shop}')

        return redirect(url_for('coffee.shops', id=shop.id))
    return render_template('shop/create.html', form=form)


@coffee_blueprint.route('/review/add', methods=['GET', 'POST'])
@login_required
def add_review():
    """
    Standard GET and POST form combination to add a review for a store

    Note that you *must* have the shop_id as one of the GET parameters,
    otherwise you will be redirected to the search page.
    """
    form = ReviewForm()
    if form.validate_on_submit():
        shop = Shop.query.get(int(form.shop_id.data))
        rating = form.rating.data
        comment = form.comment.data or None

        review = Review(rating=rating, comment=comment, shop=shop, user=current_user)
        db.session.add(review)
        db.session.commit()
        current_app.logger.info(f'Created new {review}')

        return redirect(url_for('coffee.shops', id=shop.id))

    try:
        shop_id = request.args['shop_id']
    except KeyError:
        flash('You need to have a shop to review!')
        return redirect(url_for('coffee.search_shop'))

    shop = Shop.query.get(shop_id)
    return render_template('shop/add_review.html', shop=shop, form=form)


