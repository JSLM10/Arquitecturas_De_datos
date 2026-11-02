select
    cast(review_id as bigint) as review_id,
    cast(customer_id as bigint) as customer_id,
    cast(product_id as bigint) as product_id,
    cast(rating as integer) as rating,
    cast(reviewed_at as timestamptz) as reviewed_at,
    -- Redshift no permite cast de texto a boolean: se traduce el texto del JSON a mano.
    case lower(json_extract_path_text(document_json, 'verification', 'purchase_confirmed'))
        when 'true' then true
        when 'false' then false
    end as is_verified_purchase,
    document_json,
    _batch_id,
    _loaded_at,
    _source
from {{ latest_by_key(source('mongodb_raw', 'mongo_reviews'), 'review_id') }} as latest
