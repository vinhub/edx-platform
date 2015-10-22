// Backbone.js Application Collection: CertificateWhiteList
/*global define, RequireJS */

;(function(define){
    'use strict';
    define([
            'backbone',
            'gettext',
            'js/certificates/models/certificate_exception'
        ],

        function(Backbone, gettext, CertificateExceptionModel){

            var CertificateWhiteList =  Backbone.Collection.extend({
                model: CertificateExceptionModel,

                initialize: function(attrs, options){
                    this.url = options.url;
                },

                getModel: function(attrs){
                    var model = this.findWhere({user_name: attrs.user_name});
                    if(attrs.user_name && model){
                        return model;
                    }
                    else if(attrs.user_email){
                        return this.findWhere({user_email: attrs.user_email});
                    }
                    else{
                        return undefined;
                    }
                },

                sync: function(options, appended_url){
                    var filtered = this.filter(function(model){
                        return model.isNew();
                    });

                    Backbone.sync(
                        'create',
                        new CertificateWhiteList(filtered, {url: this.url + appended_url}),
                        options
                    );
                },

                parse: function (certificate_white_list_json) {
                    // Transforms the provided JSON into a CertificateWhiteList collection
                    var modelArray = this.certificate_whitelist(certificate_white_list_json);

                    for (var i in modelArray) {
                        if (modelArray.hasOwnProperty(i)) {
                            this.push(modelArray[i]);
                        }
                    }
                    return this.models;
                },

                certificate_whitelist: function(certificate_white_list_json) {
                    var return_array;

                    try {
                        return_array = JSON.parse(certificate_white_list_json);
                    } catch (ex) {
                        // If it didn't parse, and `certificate_whitelist_json` is an object then return as it is
                        // otherwise return empty array
                        if (typeof certificate_white_list_json === 'object'){
                            return_array = certificate_white_list_json;
                        }
                        else {
                            console.error(
                                gettext('Could not parse certificate JSON. %(message)s'),
                                {message: ex.message},
                                true
                            );
                            return_array = [];
                        }
                    }
                    return return_array;
                },

                update: function(data){
                    _.each(data, function(item){
                        var certificate_exception_model =
                            this.getModel({user_name: item.user_name, user_email: item.user_email});
                        certificate_exception_model.set(item);
                    }, this);
                }
            });

            return CertificateWhiteList;
        }
    );
}).call(this, define || RequireJS.define);