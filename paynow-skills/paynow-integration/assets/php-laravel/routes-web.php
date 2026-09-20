<?php

// routes/web.php — Paynow routes.

use App\Http\Controllers\PaynowController;
use Illuminate\Support\Facades\Route;

Route::post('/checkout/paynow', [PaynowController::class, 'checkout'])
    ->name('paynow.checkout');

Route::post('/checkout/paynow/mobile', [PaynowController::class, 'checkoutMobile'])
    ->name('paynow.checkout.mobile');

// The resulturl. Server-to-server, no session, no CSRF token — see below.
Route::post('/paynow/callback', [PaynowController::class, 'callback'])
    ->name('paynow.callback');

// The returnurl. Cosmetic: the browser lands here after payment.
Route::get('/paynow/return', [PaynowController::class, 'returnFromPaynow'])
    ->name('paynow.return');

// Front-end polling target, so the browser never sees the Paynow poll URL.
Route::get('/paynow/status/{ref}', [PaynowController::class, 'status'])
    ->name('paynow.status');

/*
|--------------------------------------------------------------------------
| CSRF exemption — do not skip this
|--------------------------------------------------------------------------
| Paynow POSTs the status update server-to-server with no CSRF token. Without
| an exemption Laravel returns 419, Paynow retries ten times and gives up, and
| no order is ever fulfilled — with nothing in your logs that points at CSRF.
|
| Laravel 11+ — bootstrap/app.php:
|
|     ->withMiddleware(function (Middleware $middleware) {
|         $middleware->validateCsrfTokens(except: ['paynow/callback']);
|     })
|
| Laravel 10 and earlier — app/Http/Middleware/VerifyCsrfToken.php:
|
|     protected $except = ['paynow/callback'];
*/
