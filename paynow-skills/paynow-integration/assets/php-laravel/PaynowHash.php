<?php

declare(strict_types=1);

namespace App\Services\Paynow;

/**
 * SHA-512 hashing for Paynow messages.
 *
 * Two things make Paynow hashes fail in practice, and both are handled here:
 * field ORDER (the digest depends on it, so nothing may reorder the fields) and
 * COMPLETENESS (Paynow returns fields the docs don't list - paynowreference is a
 * common one - and they are part of the digest, so never hash a fixed list).
 *
 * Proven against Paynow's two published fixtures - see PaynowHashTest.
 */
final class PaynowHash
{
    /**
     * The integration key is lower-cased before hashing.
     *
     * Both official SDKs do this - the PHP SDK in its constructor and again in
     * initiateTransaction(), the Node SDK inside generateHash() - so a key that
     * arrives upper-cased still produces the digest Paynow expects. Paynow's
     * published keys are lower-case, which is why this is easy to miss: skip it
     * and the helper works in every example and fails on a real upper-cased key.
     */
    public function __construct(private string $integrationKey)
    {
        $this->integrationKey = strtolower($integrationKey);
    }

    /** $values in message order; a 'hash' entry is ignored if present. */
    public function generate(array $values): string
    {
        $concat = '';
        foreach ($values as $key => $value) {
            if (strtoupper((string) $key) === 'HASH') {
                continue;
            }
            $concat .= $value;
        }

        return strtoupper(hash('sha512', $concat . $this->integrationKey));
    }

    /** $values: already URL-decoded key => value pairs, in arrival order. */
    public function verify(array $values): bool
    {
        $received = null;
        foreach ($values as $key => $value) {
            if (strtoupper((string) $key) === 'HASH') {
                $received = $value;
            }
        }

        if ($received === null) {
            return false;
        }

        return hash_equals($this->generate($values), strtoupper((string) $received));
    }

    /**
     * Parse "a=1&b=2" into an ORDERED, URL-decoded array.
     *
     * Deliberately not parse_str(): it mangles keys containing dots or spaces and
     * gives no ordering guarantee, which is exactly what the digest depends on.
     */
    public static function parseResponse(string $body): array
    {
        $out = [];
        foreach (explode('&', trim($body)) as $pair) {
            if ($pair === '') {
                continue;
            }
            $parts = explode('=', $pair, 2);
            $out[urldecode($parts[0])] = isset($parts[1]) ? urldecode($parts[1]) : '';
        }

        return $out;
    }

    /**
     * Verify a Links & Buttons Notification URL POST.
     *
     * Different algorithm on purpose: key+value, not values alone.
     */
    public static function verifyNotification(array $post, string $integrationKey): bool
    {
        $concat = '';
        $received = null;

        foreach ($post as $key => $value) {
            if (strcasecmp((string) $key, 'Hash') === 0) {
                $received = $value;
                continue;
            }
            $concat .= $key . $value;
        }

        $integrationKey = strtolower($integrationKey);   // as the SDKs do

        if ($received === null) {
            return false;
        }

        return hash_equals(
            strtoupper(hash('sha512', $concat . $integrationKey)),
            strtoupper((string) $received)
        );
    }
}
