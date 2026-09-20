<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::table('orders', function (Blueprint $table) {
            // The only handle on the transaction after initiation.
            $table->string('poll_url')->nullable();

            // Paynow's own reference, for reconciliation and support tickets.
            $table->string('paynow_reference')->nullable();

            // Unique per Express Checkout request, and the ONLY way back to a
            // request whose response was lost to a timeout (/interface/trace).
            // Only fill this with a value you actually sent to Paynow. The PHP
            // SDK's sendMobile() cannot send one, so on that path the column
            // stays null; it is populated when you initiate over raw HTTP.
            $table->string('merchant_trace', 32)->nullable()->unique();

            $table->string('payment_status')->default('pending');

            // Set once, when fulfilment happens. Reading this before doing work is
            // what makes the callback idempotent under Paynow's retries.
            $table->timestamp('fulfilled_at')->nullable();

            $table->index('payment_status');
        });
    }

    public function down(): void
    {
        Schema::table('orders', function (Blueprint $table) {
            $table->dropIndex(['payment_status']);
            $table->dropColumn([
                'poll_url', 'paynow_reference', 'merchant_trace',
                'payment_status', 'fulfilled_at',
            ]);
        });
    }
};
