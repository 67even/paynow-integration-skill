<?php

// Merge into config/services.php

return [

    'paynow' => [
        'id' => env('PAYNOW_INTEGRATION_ID'),
        'key' => env('PAYNOW_INTEGRATION_KEY'),

        // In test mode only the merchant account that owns the integration can
        // complete a payment, so authemail must be a merchant login address.
        // Getting this wrong locks you out of your own test transactions.
        'test_mode' => env('PAYNOW_TEST_MODE', true),
        'merchant_email' => env('PAYNOW_MERCHANT_EMAIL'),
    ],

];
