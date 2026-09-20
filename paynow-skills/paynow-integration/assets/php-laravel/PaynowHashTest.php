<?php

declare(strict_types=1);

namespace Tests\Unit;

use App\Services\Paynow\PaynowGateway;
use App\Services\Paynow\PaynowHash;
use PHPUnit\Framework\TestCase;

/**
 * Paynow's two published fixtures, plus the two behaviours that cost money.
 *
 * Write these before anything else. A hashing helper proven against the fixtures
 * removes the largest single class of Paynow bugs, and the Awaiting Delivery case
 * is the one that otherwise only shows up in production.
 */
final class PaynowHashTest extends TestCase
{
    private const KEY = '3e9fed89-60e1-4ce5-ab6e-6b1eb2d4f977';

    public function test_outbound_fixture(): void
    {
        $hasher = new PaynowHash(self::KEY);

        $fields = [
            'id' => '1201',
            'reference' => 'TEST REF',
            'amount' => '99.99',
            'additionalinfo' => 'A test ticket transaction',
            'returnurl' => 'http://www.google.com/search?q=returnurl',
            'resulturl' => 'http://www.google.com/search?q=resulturl',
            'status' => 'Message',
        ];

        $this->assertSame(
            '2A033FC38798D913D42ECB786B9B19645ADEDBDE788862032F1BD82CF3B92DEF'
            .'84F316385D5B40DBB35F1A4FD7D5BFE73835174136463CDD48C9366B0749C689',
            $hasher->generate($fields)
        );
    }

    public function test_inbound_fixture_verifies(): void
    {
        $body = 'status=Ok'
            .'&browserurl=https%3a%2f%2fstaging.paynow.co.zw%2fPayment%2fConfirmPayment%2f9510'
            .'&pollurl=https%3a%2f%2fstaging.paynow.co.zw%2fInterface%2fCheckPayment%2f'
            .'%3fguid%3dc7ed41da-0159-46da-b428-69549f770413'
            .'&paynowreference=9510'
            .'&hash=750DD0B0DF374678707BB5AF915AF81C228B9058AD57BB7120569EC68BBB9C2E'
            .'FC1B26C6375D2BC562AC909B3CD6B2AF1D42E1A5E479FFAC8F4FB3FDCE71DF4D';

        $this->assertTrue(
            (new PaynowHash(self::KEY))->verify(PaynowHash::parseResponse($body))
        );
    }

    public function test_a_tampered_message_is_rejected(): void
    {
        $body = 'status=Ok&amount=1.00&hash=DEADBEEF';

        $this->assertFalse(
            (new PaynowHash(self::KEY))->verify(PaynowHash::parseResponse($body))
        );
    }

    /**
     * Both official SDKs lower-case the integration key before hashing. Paynow's
     * published keys are already lower-case, so a helper that skips this passes
     * every documented fixture and then fails on a real upper-cased key.
     */
    public function test_key_case_does_not_change_the_digest(): void
    {
        $fields = ['id' => '1201', 'reference' => 'TEST REF', 'status' => 'Message'];

        $this->assertSame(
            (new PaynowHash(self::KEY))->generate($fields),
            (new PaynowHash(strtoupper(self::KEY)))->generate($fields)
        );
    }

    /**
     * The one that matters. Awaiting Delivery means the customer HAS paid - Paynow
     * is holding the funds until delivery is confirmed. Anything that treats it as
     * unpaid strands real orders, and that is exactly what the SDK's paid() does.
     */
    public function test_all_three_paid_states_count_as_paid(): void
    {
        $gateway = new PaynowGateway('1', self::KEY, 'https://example.com/cb');

        foreach (['Paid', 'Awaiting Delivery', 'Delivered'] as $status) {
            $this->assertTrue($gateway->isPaid($status), "$status should count as paid");
        }

        foreach (['Created', 'Sent', 'Cancelled', 'Refunded', 'Disputed'] as $status) {
            $this->assertFalse($gateway->isPaid($status), "$status should not count as paid");
        }
    }
}
