<?php

declare(strict_types=1);

namespace App\Http\Controllers;

use App\Jobs\FulfilOrder;
use App\Models\Order;
use App\Services\Paynow\PaynowException;
use App\Services\Paynow\PaynowGateway;
use App\Services\Paynow\PaynowHash;
use Illuminate\Http\Request;

class PaynowController extends Controller
{
    public function __construct(private PaynowGateway $paynow)
    {
    }

    /** POST /checkout/paynow */
    public function checkout(Request $request)
    {
        $order = $request->user()->currentOrder();

        try {
            $result = $this->paynow->initiateWeb(
                reference: $order->reference,
                items: $order->items->map(fn ($i) => [
                    'name' => $i->name,
                    'price' => round($i->price * $i->qty, 2),
                ])->all(),
                customerEmail: $order->customer_email,
                returnUrl: route('paynow.return', ['ref' => $order->reference]),
            );
        } catch (PaynowException $e) {
            report($e);

            return back()->withErrors('Could not start the payment. Please try again.');
        }

        // Persist the poll URL BEFORE redirecting. It is the only handle on the
        // transaction afterwards; a crash between redirect and save leaves a paying
        // customer and an order that cannot be resolved.
        $order->update([
            'poll_url' => $result['poll_url'],
            'payment_status' => 'initiated',
        ]);

        return redirect()->away($result['redirect_url']);
    }

    /** POST /checkout/paynow/mobile  — EcoCash / OneMoney */
    public function checkoutMobile(Request $request)
    {
        $validated = $request->validate([
            'phone' => ['required', 'string'],
            'method' => ['required', 'in:ecocash,onemoney'],
        ]);

        $order = $request->user()->currentOrder();

        try {
            $result = $this->paynow->initiateMobile(
                reference: $order->reference,
                items: $order->items->map(fn ($i) => [
                    'name' => $i->name,
                    'price' => round($i->price * $i->qty, 2),
                ])->all(),
                customerEmail: $order->customer_email,
                phone: $validated['phone'],
                method: $validated['method'],
                returnUrl: route('paynow.return', ['ref' => $order->reference]),
            );
        } catch (PaynowException $e) {
            report($e);

            // e.g. "Insufficient balance" from test number 0774444444
            return response()->json(['error' => $e->getMessage()], 402);
        }

        $order->update([
            'poll_url' => $result['poll_url'],
            'payment_status' => 'awaiting_authorisation',
            // merchant_trace is deliberately NOT set here. The PHP SDK's
            // sendMobile() has no merchanttrace parameter, so Paynow never
            // receives one on this path - storing a locally generated UUID
            // would look like a recovery handle while being useless, because
            // /interface/trace would answer NotFound for it. If you need trace
            // recovery, initiate Express Checkout over raw HTTP instead and
            // send the value yourself: see references/raw-http.md.
        ]);

        return response()->json([
            'reference' => $order->reference,
            'instructions' => $result['instructions'],   // render verbatim
        ]);
    }

    /**
     * POST /paynow/callback  — the resulturl.
     *
     * This is the only authoritative signal that money arrived. Exempt it from CSRF
     * (bootstrap/app.php in Laravel 11+, VerifyCsrfToken before that) or it is
     * silently rejected and nothing is ever fulfilled.
     */
    public function callback(Request $request)
    {
        // Read the RAW body: the hash depends on Paynow's field order, and a
        // framework-parsed array gives no ordering guarantee.
        $fields = PaynowHash::parseResponse($request->getContent());

        if (! $this->paynow->hasher()->verify($fields)) {
            logger()->warning('[paynow] REJECTED callback: bad hash');

            return response('', 400);
        }

        $f = array_change_key_case($fields, CASE_LOWER);
        $reference = $f['reference'] ?? null;
        $status = $f['status'] ?? '';
        $amount = (float) ($f['amount'] ?? 0);

        $order = Order::where('reference', $reference)->first();

        if (! $order) {
            logger()->warning('[paynow] unknown reference', ['reference' => $reference]);

            // 200, not 404: a non-2xx makes Paynow retry this ten times.
            return response('', 200);
        }

        if ($this->paynow->isPaid($status)) {
            if ($order->isFulfilled()) {
                return response('', 200);          // idempotent: already done
            }

            if (abs($amount - (float) $order->total) > 0.001) {
                logger()->error('[paynow] AMOUNT MISMATCH', [
                    'reference' => $reference, 'got' => $amount, 'want' => $order->total,
                ]);
                $order->update(['payment_status' => 'review']);

                return response('', 200);
            }

            $order->markPaid($f['paynowreference'] ?? null, $status);
            FulfilOrder::dispatch($order);          // slow work off the request
        } elseif ($this->paynow->isTerminal($status)) {
            $order->update(['payment_status' => strtolower($status)]);
        } else {
            $order->update(['payment_status' => strtolower($status)]);   // Created / Sent
        }

        return response('', 200);
    }

    /**
     * GET /paynow/return  — cosmetic only.
     *
     * The customer's browser lands here, which proves nothing: they may have
     * abandoned the payment, or typed the URL. Render current state, fulfil nothing.
     */
    public function returnFromPaynow(Request $request)
    {
        $order = Order::where('reference', $request->query('ref'))->firstOrFail();

        return view('checkout.thanks', ['order' => $order->fresh()]);
    }

    /**
     * GET /paynow/status/{ref}  — for the front-end polling UI.
     *
     * The browser polls this, never Paynow directly: exposing the poll URL invites
     * tampering and leaks a transaction handle into the page.
     */
    public function status(Request $request, string $ref)
    {
        $order = Order::where('reference', $ref)->firstOrFail();

        if (! $order->isFulfilled() && $order->poll_url) {
            $status = $this->paynow->pollStatus($order->poll_url);

            if ($status !== null && $this->paynow->isPaid($status) && ! $order->isFulfilled()) {
                $order->markPaid(null, $status);
                FulfilOrder::dispatch($order);
            }
        }

        $fresh = $order->fresh();

        return response()->json([
            'status' => $fresh->payment_status,
            'paid' => $fresh->isFulfilled(),
        ]);
    }
}
