The review never mentions the `apiKey` JavaScript variable or `$GLOBALS['gateway_api_key']` being echoed into the page. Its closest item is #7, which discusses `$GLOBALS['assets_static_relative']` as an SSRF/script-loading risk, and #5, which covers credit card data display. Neither addresses a private payment-gateway secret key exposed to every portal user in the page source.

LABEL: Missed