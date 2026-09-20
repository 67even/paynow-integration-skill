<?php

declare(strict_types=1);

namespace App\Services\Paynow;

use Paynow\Http\ConnectionException;
use Paynow\Payments\HashMismatchException;
use Paynow\Payments\InvalidIntegrationException;
use Paynow\Payments\Paynow;

/**
 * The only place in the application that knows Paynow credentials.
 *
 * Keeping this in one class means the test-mode authemail rule, the paid-state
 * definition and the exception handling are decided once rather than re-derived
 * at every call site - which is where they usually get decided wrongly.
 */
final class PaynowGateway
{
    /**
     * All three mean the customer's money has arrived. Awaiting Delivery is held
     * in suspense until the merchant confirms delivery; Delivered is inside the
     * 24-hour confirmation window. Treating only 'Paid' as paid - which is what
     * the SDK's paid() helper does - silently strands paid orders.
     */
    public const PAID_STATUSES = ['paid', 'awaiting delivery', 'delivered'];

    public const TERMINAL_STATUSES = ['cancelled', 'refunded', 'disputed'];

    public function __construct(
        private string $integrationId,
        private string $integrationKey,
        private string $resultUrl,
        private bool $testMode = false,
        private ?string $merchantEmail = null,
    ) {
    }

    public static function fromConfig(): self
    {
        return new self(
            (string) config('services.paynow.id'),
            (string) config('services.paynow.key'),
            route('paynow.callback'),
            (bool) config('services.paynow.test_mode'),
            config('services.paynow.merchant_email'),
        );
    }

    public function hasher(): PaynowHash
    {
        return new PaynowHash($this->integrationKey);
    }

    /**
     * In test mode only the merchant account that owns the integration can log in
     * and complete a payment - everyone else is told the merchant is in testing.
     * So the auth email has to be a merchant login, or the developer locks
     * themselves out of their own test transactions.
     */
    public function authEmailFor(?string $customerEmail): ?string
    {
        return $this->testMode ? $this->merchantEmail : $customerEmail;
    }

    public function isPaid(?string $status): bool
    {
        return in_array(strtolower((string) $status), self::PAID_STATUSES, true);
    }

    public function isTerminal(?string $status): bool
    {
        return in_array(strtolower((string) $status), self::TERMINAL_STATUSES, true);
    }

    private function client(string $returnUrl): Paynow
    {
        return new Paynow(
            $this->integrationId,
            $this->integrationKey,
            $returnUrl,
            $this->resultUrl,
        );
    }

    /**
     * Start a redirect (web) transaction.
     *
     * @param  array<int, array{name: string, price: float}>  $items
     * @return array{redirect_url: string, poll_url: string}
     *
     * @throws PaynowException
     */
    public function initiateWeb(string $reference, array $items, ?string $customerEmail, string $returnUrl): array
    {
        $paynow = $this->client($returnUrl);
        $payment = $paynow->createPayment($reference, $this->authEmailFor($customerEmail));

        foreach ($items as $item) {
            $payment->add($item['name'], round((float) $item['price'], 2));
        }

        // send() throws rather than returning a failed response for the most common
        // misconfigurations, so success() is only reachable if nothing was raised.
        try {
            $response = $paynow->send($payment);
        } catch (InvalidIntegrationException $e) {
            throw new PaynowException('Paynow rejected the integration ID. Is it live?', 0, $e);
        } catch (HashMismatchException $e) {
            throw new PaynowException('Paynow response failed hash verification - not redirecting.', 0, $e);
        } catch (ConnectionException $e) {
            throw new PaynowException('Could not reach Paynow: ' . $e->getMessage(), 0, $e);
        }

        if (! $response->success()) {
            // errors() returns a space-joined string, not an array.
            throw new PaynowException('Paynow declined initiation: ' . $response->errors());
        }

        return [
            'redirect_url' => $response->redirectUrl(),
            'poll_url' => $response->pollUrl(),
        ];
    }

    /**
     * Start an EcoCash / OneMoney transaction. No redirect - the customer gets a
     * USSD prompt, so the caller needs to render the instructions and poll.
     *
     * @return array{poll_url: string, instructions: string}
     *
     * @throws PaynowException
     */
    public function initiateMobile(
        string $reference,
        array $items,
        ?string $customerEmail,
        string $phone,
        string $method,
        string $returnUrl,
    ): array {
        $paynow = $this->client($returnUrl);
        $payment = $paynow->createPayment($reference, $this->authEmailFor($customerEmail));

        foreach ($items as $item) {
            $payment->add($item['name'], round((float) $item['price'], 2));
        }

        try {
            $response = $paynow->sendMobile($payment, $phone, $method);
        } catch (InvalidIntegrationException|HashMismatchException|ConnectionException $e) {
            throw new PaynowException('Paynow mobile initiation failed: ' . $e->getMessage(), 0, $e);
        }

        if (! $response->success()) {
            // Insufficient balance fails here; a user cancellation initiates fine
            // and only fails later via the status update. Both paths need handling.
            throw new PaynowException('Paynow declined initiation: ' . $response->errors());
        }

        return [
            'poll_url' => $response->pollUrl(),
            'instructions' => $response->instructions(),
        ];
    }

    /**
     * Poll a transaction. Returns the lower-cased status word, or null on failure.
     *
     * Note this returns the word rather than a boolean: callers sometimes need to
     * distinguish "still pending" from "cancelled", and a boolean throws that away.
     */
    public function pollStatus(string $pollUrl, string $returnUrl = 'https://example.com/'): ?string
    {
        try {
            $status = $this->client($returnUrl)->pollTransaction($pollUrl);
        } catch (\Throwable $e) {
            report($e);

            return null;
        }

        return $status->status();   // already lower-cased by the SDK
    }
}
